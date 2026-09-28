"""Exercise the Windows credential pointer protocol without launching Windows Python."""

import ctypes

from tcm_platform import model_credentials


def test_credential_write_read_and_free_with_winapi_standin(monkeypatch):
    class FakeApi:
        def __init__(self):
            self.saved = {}
            self.live = []
            self.freed = 0

        def CredWriteW(self, pointer, flags):
            credential = ctypes.cast(pointer, ctypes.POINTER(
                model_credentials._CREDENTIALW)).contents
            self.saved[credential.TargetName] = ctypes.string_at(
                credential.CredentialBlob, credential.CredentialBlobSize)
            assert credential.Type == 1 and credential.Persist == 2
            return 1

        def CredReadW(self, target, credential_type, flags, pointer):
            assert credential_type == 1 and flags == 0
            blob = ctypes.create_string_buffer(self.saved[target])
            credential = model_credentials._CREDENTIALW()
            credential.CredentialBlobSize = len(self.saved[target])
            credential.CredentialBlob = ctypes.cast(blob, ctypes.POINTER(ctypes.c_ubyte))
            self.live.append((blob, credential))
            output = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(
                model_credentials._CREDENTIALW)))
            output[0] = ctypes.pointer(credential)
            return 1

        def CredFree(self, pointer):
            self.freed += 1

    fake = FakeApi()
    monkeypatch.setattr(model_credentials, "_credential_api", lambda: fake)
    model_credentials.store_model_key("siliconflow", "synthetic-test-secret")
    assert fake.saved["tcm-research-platform:siliconflow"]
    assert model_credentials.read_model_key("siliconflow") == "synthetic-test-secret"
    assert fake.freed == 1
