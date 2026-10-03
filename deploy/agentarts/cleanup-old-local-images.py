"""User-run, exact local image cleanup. Never accesses registry/auth files or prunes."""
import argparse,json,subprocess,sys
NEW_TAG='banfei-runtime:agentarts-swr-20261002151626'
NEW_ID='sha256:113fed6a1981c8cc71ba1586cd7556ea9925f4ff9e766614ee70b508d5ef480e'
OLD={
 'banfei-runtime:agentarts-local-20261002143953':'sha256:27075feebb4d20e0e84ca3cff12b01d6ce90c15d062e019aefaff93dc55e73c8',
 'banfei-runtime:agentarts-local-20261002145622':'sha256:4fb66eeb80725f033f56631384cfb7cdf1d197e75a62ab34cee5fa5fec48d6ba',
 'swr.cn-southwest-2.myhuaweicloud.com/banfei/banfei-runtime:agentarts-local-20261002145622':'sha256:4fb66eeb80725f033f56631384cfb7cdf1d197e75a62ab34cee5fa5fec48d6ba',
}
DOCKER=['sudo','docker','--host','unix:///var/run/docker.sock']

def cleanup(execute=False,run=subprocess.run):
    print('KEEP',NEW_TAG,NEW_ID,flush=True)
    for tag,image_id in OLD.items():print('REMOVE LOCAL TAG IF ID MATCHES',tag,image_id,flush=True)
    if not execute:
        print('Preview only. --execute requires local interactive sudo. No registry deletion, container removal, force or prune.')
        return
    def command(args):
        result=run(args,text=True,capture_output=True)
        if result.returncode:raise RuntimeError('Command failed: '+result.stderr.strip())
        return result.stdout.strip()
    # Local user authenticates. Password input is handled by sudo, never Python.
    if run(['sudo','-v']).returncode:raise RuntimeError('Local sudo authentication was not completed')
    if command(DOCKER+['image','inspect',NEW_TAG,'--format','{{.Id}}'])!=NEW_ID:
        raise RuntimeError('Current successful image missing or changed; nothing deleted')
    candidates=[]
    for tag,expected in OLD.items():
        result=run(DOCKER+['image','inspect',tag,'--format','{{.Id}}'],text=True,capture_output=True)
        if result.returncode:
            if 'No such image' in result.stderr:
                print('ALREADY ABSENT',tag,flush=True);continue
            raise RuntimeError('Cannot inspect old image; nothing deleted: '+result.stderr.strip())
        if result.stdout.strip()!=expected:raise RuntimeError('Old tag was reassigned; nothing deleted: '+tag)
        candidates.append((tag,expected))
    for image_id in sorted({value for _,value in candidates}):
        containers=command(DOCKER+['ps','-a','--filter','ancestor='+image_id,'--format','{{.ID}} {{.Image}} {{.Status}}'])
        if containers:raise RuntimeError('Related containers exist; stop without deleting images or containers: '+containers)
    for tag,expected in candidates:
        # Recheck immediately before each non-forced deletion.
        if command(DOCKER+['image','inspect',tag,'--format','{{.Id}}'])!=expected:
            raise RuntimeError('Tag changed during cleanup; remaining actions stopped: '+tag)
        print(command(DOCKER+['image','rm','--no-prune','--',tag]),flush=True)
    if command(DOCKER+['image','inspect',NEW_TAG,'--format','{{.Id}}'])!=NEW_ID:
        raise RuntimeError('New image verification failed')
    print('DONE: known old tags removed; new image retained. Unlisted aliases/cache and all evidence untouched.',flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute',action='store_true')
    args=parser.parse_args()
    try:cleanup(args.execute)
    except RuntimeError as error:
        print('STOP:',str(error),file=sys.stderr)
        raise SystemExit(1)
