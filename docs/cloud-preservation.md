# Preserve and verify the cloud environment

GitHub preserves committed source on the pushed branches. It does not preserve
the installed virtual environment, ignored local artifacts or a cloud snapshot.
Likewise, a saved environment draft does not prove publication or restoration.

The draft has installation and startup instructions for this checkout. The agent
can inspect that draft and the current machine, but publication and reopening
must be confirmed through the product interface. Neither is established by this
document or by the application's test results.

## User-operated verification

1. Open the cloud environment settings associated with this task.
2. Review the installation script and startup instructions. They use the existing
   checkout, the hashed dependency lock and mock-mode readiness checks. Preserve
   any other settings you need, then save the draft.
3. Publish the environment snapshot if that action is available. Wait for the
   interface to confirm publication; saving a draft alone is not sufficient.
4. Reopen or start a task using that published environment through the product UI.
   Verify the restored repository and interpreter from its terminal:

   ```sh
   cd /workspace/AI-agent-workflow-portfolio-project-
   git status --short
   git log -1 --oneline
   .venv/bin/python --version
   .venv/bin/python -m operations_agent samples/invoice.txt --format text --mode mock --orchestrate --known-vendor 'Demo Supplies'
   ```

5. Check that the expected source commit is present, the interpreter is usable,
   and the sample exits 0 with valid validation, no workflow issues and a pending
   human decision. The sample does not make provider calls. Run the full test
   command from the README when verifying the restored development workflow.

If restoration has not been verified, keep it recorded as unverified. No service
process needs to survive publication for the CLI. If using the optional workbench,
restart it with the command in [its guide](workbench.md). Provider credentials
remain separate environment configuration and are unnecessary for these checks.

If only the GitHub source is available, select the pushed project branch and
recreate `.venv` from `requirements.lock` using the README. This recovers the
development workflow, not the contents of a previously unverified cloud snapshot.
