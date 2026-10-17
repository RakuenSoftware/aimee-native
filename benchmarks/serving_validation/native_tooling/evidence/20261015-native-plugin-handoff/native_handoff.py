"""Private research: request-bound completion handoff, with owner-only decisions.

No capability parser, resource binding, revision ordering, or tool execution lives
here. Runtime and owner transports are injected; this is not an HTTP endpoint.
"""
from dataclasses import dataclass
from dataclasses import asdict
import asyncio
import hashlib
import json
from typing import Protocol


@dataclass(frozen=True)
class Request:
    actor: str
    session: str
    request_id: str
    task_id: str


@dataclass(frozen=True)
class Publication:
    revision: str
    content: str


@dataclass(frozen=True)
class Contribution:
    request: Request
    ordinal: int
    revision: str
    publication_sha256: str
    text: str
    finish_reason: str


@dataclass(frozen=True)
class OwnerReply:
    request: Request
    ordinal: int
    publication_sha256: str
    state: str  # resume, complete, clarify, refusal
    publication: Publication | None = None
    output: str = ""


class Owner(Protocol):
    async def open(self, request: Request) -> Publication: ...
    async def contribute(self, contribution: Contribution) -> OwnerReply: ...
    async def close(self, request: Request, reason: str) -> None: ...


class Runtime(Protocol):
    async def publish(self, publication: Publication) -> None: ...
    async def generate(self, request: Request, publication: Publication) -> tuple[str, str]: ...
    async def withdraw(self) -> None: ...


class HandoffError(RuntimeError):
    pass


class UnixOwner:
    """Private JSONL transport. Socket custody/authentication belongs to deployment.

    This research transport must use an owner-controlled directory/socket; it is
    not a replacement for the enrolled Aimee identity and authorization channel.
    """

    def __init__(self, socket_path, *, timeout_seconds=240):
        self.socket_path, self.timeout_seconds = socket_path, timeout_seconds

    async def _call(self, op, payload):
        async with asyncio.timeout(self.timeout_seconds):
            reader, writer = await asyncio.open_unix_connection(self.socket_path, limit=262144)
            try:
                raw = json.dumps(dict(op=op, **payload), ensure_ascii=False).encode() + b"\n"
                if len(raw) > 262144:
                    raise HandoffError("owner frame too large")
                writer.write(raw)
                await writer.drain()
                line = await reader.readline()
                if not line.endswith(b"\n"):
                    raise HandoffError("incomplete owner frame")
                response = json.loads(line)
                if response.get("error"):
                    raise HandoffError("owner refused handoff: " + str(response['error']))
                return response
            finally:
                writer.close()
                await writer.wait_closed()

    async def open(self, request):
        response = await self._call("open", dict(request=asdict(request)))
        if response.get('request') != asdict(request):
            raise HandoffError("owner open binding mismatch")
        return Publication(**response['publication'])

    async def contribute(self, contribution):
        response = await self._call("contribute", dict(contribution=asdict(contribution)))
        response['request'] = Request(**response['request'])
        if response.get('publication') is not None:
            response['publication'] = Publication(**response['publication'])
        return OwnerReply(**response)

    async def close(self, request, reason):
        response = await self._call("close", dict(request=asdict(request), reason=reason))
        if response != dict(closed=True, request=asdict(request)):
            raise HandoffError("owner close binding mismatch")


def digest(publication: Publication) -> str:
    return hashlib.sha256(publication.content.encode("utf-8")).hexdigest()


class NativeHandoff:
    """One exclusive CPU publication lane; terminal output requires an owner reply.

    Timeout/cancellation drains or invalidates runtime state through withdraw.
    Runtime.generate must complete worker release before returning, and its
    withdraw implementation must refuse reuse when release cannot be confirmed.
    """

    def __init__(self, runtime: Runtime, owner: Owner, *, max_rounds=3,
                 timeout_seconds=1800, cleanup_seconds=30):
        if type(max_rounds) is not int or not 1 <= max_rounds <= 16:
            raise ValueError("invalid contribution budget")
        if timeout_seconds <= 0 or cleanup_seconds <= 0:
            raise ValueError("invalid deadline")
        self.runtime, self.owner = runtime, owner
        self.max_rounds, self.timeout_seconds = max_rounds, timeout_seconds
        self.cleanup_seconds = cleanup_seconds
        self._lane = asyncio.Lock()
        self._poisoned = False

    async def run(self, request: Request) -> OwnerReply:
        if any(not isinstance(v, str) or not v or len(v) > 256
               for v in (request.actor, request.session, request.request_id, request.task_id)):
            raise ValueError("invalid request binding")
        async with self._lane:
            if self._poisoned:
                raise HandoffError("runtime cleanup unconfirmed; restart required")
            reason = "failed"
            try:
                async with asyncio.timeout(self.timeout_seconds):
                    publication = await self.owner.open(request)
                    for ordinal in range(self.max_rounds):
                        if (not isinstance(publication, Publication)
                                or not publication.revision or len(publication.revision) > 128
                                or not publication.content
                                or len(publication.content.encode("utf-8")) > 65536):
                            raise HandoffError("invalid owner publication")
                        await self.runtime.publish(publication)
                        text, finish = await self.runtime.generate(request, publication)
                        if finish != "stop":
                            raise HandoffError("nonterminal contribution cannot dispatch")
                        if not isinstance(text, str) or not text or len(text.encode("utf-8")) > 65536:
                            raise HandoffError("invalid contribution")
                        proposal = Contribution(request, ordinal, publication.revision,
                                                digest(publication), text, finish)
                        reply = await self.owner.contribute(proposal)
                        if (not isinstance(reply, OwnerReply) or reply.request != request
                                or reply.ordinal != ordinal
                                or reply.publication_sha256 != proposal.publication_sha256):
                            raise HandoffError("owner reply binding mismatch")
                        if reply.state == "resume" and reply.publication is not None:
                            publication = reply.publication
                            continue
                        if reply.state in ("complete", "clarify", "refusal") and reply.publication is None:
                            reason = reply.state
                            return reply
                        raise HandoffError("invalid owner transition")
                    raise HandoffError("contribution budget exhausted")
            except asyncio.CancelledError:
                reason = "cancelled"
                raise
            finally:
                # Both cleanups run even if either transport fails. Failure poisons
                # this lane; no subsequent request can inherit uncertain state.
                self._poisoned = True
                results = await asyncio.gather(
                    asyncio.wait_for(self.runtime.withdraw(), self.cleanup_seconds),
                    asyncio.wait_for(self.owner.close(request, reason), self.cleanup_seconds),
                    return_exceptions=True,
                )
                if any(isinstance(result, BaseException) for result in results):
                    raise HandoffError("handoff cleanup failed; restart required")
                self._poisoned = False
