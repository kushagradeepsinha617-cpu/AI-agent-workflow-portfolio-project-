"""Local runtime configuration for the explicitly pinned CrewAI release.

CrewAI 1.15.30 initializes TokenManager during import even with tracing disabled.
Its credential path ignores CREWAI_STORAGE_DIR. This small, version-checked
compatibility adapter redirects that path; it never reads or copies home tokens.
Remove this adapter when upgrading to a release with a configurable auth path.
"""
from importlib.metadata import version
import os
from pathlib import Path


def configure_runtime():
    if version('crewai') != '1.15.30':
        raise RuntimeError('Recheck the CrewAI runtime adapter before changing the pinned release')
    os.environ['OTEL_SDK_DISABLED'] = 'true'
    os.environ['CREWAI_DISABLE_TELEMETRY'] = 'true'
    os.environ['CREWAI_TRACING_ENABLED'] = 'false'
    storage = Path(os.environ.setdefault('CREWAI_STORAGE_DIR', str(
        Path(__file__).resolve().parents[1] / 'local-data/crewai'))).resolve()

    # Verified against the pinned release's source. This is deliberately the
    # only private-framework compatibility override; no TLS/auth bypass occurs.
    from crewai_core.token_manager import TokenManager

    def local_credential_path():
        path = storage / 'credentials'
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        return path

    TokenManager._get_secure_storage_path = staticmethod(local_credential_path)
