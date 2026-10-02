python3 <<'AIMEE_EDIT_181591653cb01e3e90ad3065'
from pathlib import Path
p=Path('requests/adapters.py');s=p.read_text().splitlines(True)
s[413:415]=r"""        except (_SSLError, _HTTPError, ProtocolError) as e:
            if isinstance(e, _SSLError):
                raise SSLError(e, request=request)
            elif isinstance(e, ReadTimeoutError):
                raise ReadTimeout(e, request=request)
            elif isinstance(e, ProtocolError):
                raise ConnectionError(e, request=request)
            else:
                raise ConnectionError(e, request=request)
""".splitlines(True)
s[22:22]=r"""from .packages.urllib3.exceptions import ProtocolError
""".splitlines(True)
p.write_text(''.join(s))
p=Path('requests/models.py');s=p.read_text().splitlines(True)
s[640:640]=r"""                    raise ConnectionError(e)
                    raise ConnectionError(e)
""".splitlines(True)
p.write_text(''.join(s))
AIMEE_EDIT_181591653cb01e3e90ad3065
