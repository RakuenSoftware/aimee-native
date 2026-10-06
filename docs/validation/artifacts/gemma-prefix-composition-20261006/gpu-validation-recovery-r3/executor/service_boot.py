import os,sys
from aimee_gemma4_12b.cli import command
def main():
    args,env=command(sys.argv[1]);os.environ.update(env)
# A separate test plugin calls actual installed model registration, then
# chooses a subclass that delegates unchanged native attention math.
    os.environ['VLLM_PLUGINS']='gemma_integration_trace'
    sys.argv=args
    from vllm.entrypoints.cli.main import main as serve
    serve()

if __name__=='__main__':
    main()
