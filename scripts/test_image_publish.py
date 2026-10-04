"""Offline shell integration tests: no real sudo, Docker, auth file or network."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
POC = ROOT.parent / "banfei-agentarts-poc/scripts/build_model_proxy_runtime.sh"
FAKE = r"""#!/usr/bin/python3
import json,os,pathlib,sys
a=sys.argv[1:]
root=pathlib.Path(os.environ["FAKE_STATE"])
with (root/"calls").open("a") as f: f.write(json.dumps(a)+"\n")
assert a[:1]==["--config"], a
a=a[2:]
mode=os.environ.get("FAKE_MODE","ok")
if a[:2]==["image","inspect"]:
 if not (root/"built").exists(): sys.exit(1)
 print(json.dumps([{"Id":"sha256:local","Os":"linux","Architecture":"amd64" if mode=="bad-arch" else "arm64",
 "Descriptor":{"mediaType":"application/vnd.docker.distribution.manifest.v2+json"},
 "Config":{"User":"10001:10001"}}]))
elif a[:2]==["buildx","build"]:
 if mode=="build-fails": sys.exit(1)
 (root/"built").touch()
elif a[:2]==["manifest","inspect"]:
 if mode=="collision": print("{}"); sys.exit(0)
 print("unauthorized" if mode=="auth-fails" else "manifest unknown",file=sys.stderr); sys.exit(1)
elif a[:1]==["tag"]: pass
elif a[:1]==["push"]:
 if mode=="push-fails": print("unauthorized",file=sys.stderr); sys.exit(1)
 if mode!="missing-digest": print("new: digest: sha256:"+"a"*64+" size: 123")
else: raise AssertionError(a)
"""
class ImagePublishTests(unittest.TestCase):
    def run_case(self, mode="ok", args=(), config=None):
        with tempfile.TemporaryDirectory(prefix="banfei-image-shell-") as temp:
            base=Path(temp); binaries=base/"bin"; binaries.mkdir()
            (binaries/"docker").write_text(FAKE)
            (binaries/"sudo").write_text(
                '#!/bin/bash\nif [[ "$1" == "-v" ]]; then exit 0; fi\n'
                '[[ "$1" == docker ]] || exit 99\nexec "$FAKE_BIN/docker" "${@:2}"\n')
            for p in binaries.iterdir(): p.chmod(0o755)
            env={k:v for k,v in os.environ.items() if k not in ("SWR_AUTH_DIR","DOCKER_CONFIG")}
            env.update(PATH=str(binaries)+":/usr/bin:/bin",FAKE_BIN=str(binaries),FAKE_STATE=temp,FAKE_MODE=mode)
            env.update(config or {})
            result=subprocess.run(["bash",str(POC),*args],env=env,text=True,capture_output=True)
            calls=[json.loads(line) for line in (base/"calls").read_text().splitlines()]
            return result,calls
    def test_success_and_same_login_directory(self):
        r,calls=self.run_case(args=("--docker-config","/tmp/synthetic auth"),config={"SWR_AUTH_DIR":"/tmp/ignored","DOCKER_CONFIG":"/tmp/ignored"})
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertTrue(all(x[:2]==["--config","/tmp/synthetic auth"] for x in calls))
        self.assertEqual(sum(x[2]=="push" for x in calls),1)
        self.assertIn("IMMUTABLE_IMAGE=swr.cn-southwest-2.myhuaweicloud.com/banfei/banfei-runtime@sha256:"+"a"*64,r.stdout)
        tag=next(x[3] for x in calls if x[2]=="push")
        self.assertRegex(tag,r":model-probe-\d{8}T\d{6}Z-[a-f0-9-]{36}$")
    def test_login_selection(self):
        for env,expected in [({},str(Path.home()/".config/banfei/docker")),({"DOCKER_CONFIG":"/tmp/ignored","SWR_AUTH_DIR":"/tmp/ignored"},str(Path.home()/".config/banfei/docker"))]:
            with self.subTest(env=env):
                r,calls=self.run_case(config=env);self.assertEqual(r.returncode,0,r.stderr)
                self.assertTrue(all(x[1]==expected for x in calls))
    def test_build_only_no_registry_or_tag(self):
        r,calls=self.run_case(args=("--build-only",));self.assertEqual(r.returncode,0,r.stderr)
        self.assertFalse(any(x[2] in ("manifest","tag","push") for x in calls))
    def test_failure_before_push(self):
        for mode in ("build-fails","bad-arch","collision","auth-fails"):
            with self.subTest(mode=mode):
                r,calls=self.run_case(mode);self.assertNotEqual(r.returncode,0)
                self.assertFalse(any(x[2]=="push" for x in calls))
    def test_push_failure_no_retry_or_success(self):
        for mode in ("push-fails","missing-digest"):
            with self.subTest(mode=mode):
                r,calls=self.run_case(mode);self.assertNotEqual(r.returncode,0)
                self.assertEqual(sum(x[2]=="push" for x in calls),1)
                self.assertNotIn("PUSHED_IMAGE=",r.stdout)
    def test_new_tag_each_invocation(self):
        tags=[]
        for _ in range(2):
            r,calls=self.run_case();self.assertEqual(r.returncode,0,r.stderr)
            tags.append(next(x[3] for x in calls if x[2]=="push"))
        self.assertNotEqual(*tags)
    def test_shell_syntax(self):
        for script in [POC,ROOT/"deploy/agentarts/image-publish.sh",ROOT/"deploy/agentarts/build-arm64-local.sh"]:
            self.assertEqual(subprocess.run(["bash","-n",str(script)]).returncode,0)
if __name__=="__main__": unittest.main(verbosity=2)
