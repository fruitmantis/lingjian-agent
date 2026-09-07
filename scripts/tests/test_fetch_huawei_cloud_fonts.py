"""Network-free failure-path checks for the font asset downloader."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('font_fetch', Path(__file__).parents[1] / 'fetch_huawei_cloud_fonts.py')
fetch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fetch)


def fixture():
    data = bytearray(48); data[:4] = b'wOF2'; data[8:12] = struct.pack('>I',48); data[12:14] = struct.pack('>H',1)
    data = bytes(data)
    entry = {'url':fetch.OFFICIAL_PREFIX+'test.woff2', 'local_filename':'test.woff2', 'size':48,
             'sha256':hashlib.sha256(data).hexdigest(), 'weight':400}
    return data,entry


class Response:
    def __init__(self,data,status=200,content_type='font/woff2',url=None):
        self.data=data; self.status=status; self.headers={'Content-Type':content_type}; self.url=url or fetch.OFFICIAL_PREFIX+'test.woff2'
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def geturl(self):return self.url
    def read(self,size):return self.data[:size]


class FontFetchTest(unittest.TestCase):
    def test_reject_empty_incomplete_and_wrong_hash(self):
        data,entry=fixture()
        for bad in [b'',data[:-1],b'HTML'+data[4:],data[:-1]+b'x']:
            with self.subTest(data=bad[:4]),self.assertRaises(ValueError):fetch.verify(bad,entry)

    def test_http_content_type_and_redirect_fail_closed(self):
        data,entry=fixture()
        with tempfile.TemporaryDirectory() as temp:
            manifest=Path(temp)/'manifest.json';manifest.write_text(json.dumps({'fonts':[entry]}))
            for response in [Response(data,status=403),Response(data,content_type='text/html'),Response(data,url='https://invalid.test/font')]:
                with self.subTest(status=response.status,type=response.headers),patch.object(fetch,'MANIFEST',manifest),patch.object(fetch.urllib.request,'urlopen',return_value=response),self.assertRaises(ValueError):
                    fetch.fetch_all(Path(temp)/'fonts')
            self.assertFalse((Path(temp)/'fonts').exists())

    def test_failed_second_download_preserves_existing_set(self):
        data,entry=fixture();second={**entry,'local_filename':'second.woff2'}
        with tempfile.TemporaryDirectory() as temp:
            destination=Path(temp)/'fonts';destination.mkdir();(destination/'test.woff2').write_bytes(b'previous')
            manifest=Path(temp)/'manifest.json';manifest.write_text(json.dumps({'fonts':[entry,second]}))
            with patch.object(fetch,'MANIFEST',manifest),patch.object(fetch.urllib.request,'urlopen',side_effect=[Response(data),OSError('offline')]),self.assertRaises(OSError):fetch.fetch_all(destination)
            self.assertEqual((destination/'test.woff2').read_bytes(),b'previous')
            self.assertFalse((destination/'second.woff2').exists())

    def test_success_then_local_check_needs_no_network(self):
        data,entry=fixture()
        with tempfile.TemporaryDirectory() as temp:
            destination=Path(temp)/'fonts';manifest=Path(temp)/'manifest.json';manifest.write_text(json.dumps({'fonts':[entry]}))
            with patch.object(fetch,'MANIFEST',manifest),patch.object(fetch.urllib.request,'urlopen',return_value=Response(data)):
                result=fetch.fetch_all(destination)
            with patch.object(fetch,'MANIFEST',manifest),patch.object(fetch.urllib.request,'urlopen',side_effect=AssertionError('network forbidden')):
                self.assertEqual(result,fetch.fetch_all(destination,check_only=True))

    def test_reject_unapproved_source_and_filename(self):
        _,entry=fixture()
        with tempfile.TemporaryDirectory() as temp:
            manifest=Path(temp)/'manifest.json'
            for invalid in [{**entry,'url':'https://third-party.test/font.woff2'},{**entry,'local_filename':'../font.woff2'}]:
                manifest.write_text(json.dumps({'fonts':[invalid]}))
                with patch.object(fetch,'MANIFEST',manifest),self.assertRaises(ValueError):fetch.fetch_all(Path(temp)/'fonts')


if __name__=='__main__':unittest.main()
