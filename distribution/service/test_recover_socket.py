import pathlib
import socket
import tempfile
import unittest
from recover_socket import recover


class Recovery(unittest.TestCase):
    def test_stale_socket_removed_but_live_and_other_files_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = pathlib.Path(temporary) / 'delivery.sock'
            recover(str(path))
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
                listener.bind(str(path))
                path.chmod(0o600)
                listener.listen(1)
                with self.assertRaises(RuntimeError):
                    recover(str(path))
                self.assertTrue(path.exists())
            recover(str(path))
            self.assertFalse(path.exists())
            path.write_text('owned non-socket')
            path.chmod(0o600)
            with self.assertRaises(ValueError):
                recover(str(path))
            self.assertEqual(path.read_text(), 'owned non-socket')
            alias = path.with_name('alias')
            alias.symlink_to(path)
            with self.assertRaises(ValueError):
                recover(str(alias))
            self.assertTrue(alias.is_symlink())


if __name__ == '__main__':
    unittest.main()
