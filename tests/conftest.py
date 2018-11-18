from click.testing import CliRunner
import pytest
from wandb.history import History
from .api_mocks import *
import wandb


@pytest.fixture
def history():
    with CliRunner().isolated_filesystem():
        yield History("wandb-history.jsonl")

@pytest.fixture
def wandb_init_run(request, tmpdir, request_mocker, upsert_run, query_run_resume_status, upload_logs, monkeypatch):
    """Fixture that calls wandb.init(), yields the run that
    gets created, then cleans up afterward.
    """
    # save the environment so we can restore it later. pytest
    # may actually do this itself. didn't check.
    orig_environ = dict(os.environ)
    try:
        if request.node.get_marker('jupyter'):
            upsert_run(request_mocker)
            query_run_resume_status(request_mocker)

            def get_ipython():
                class Jupyter(object):
                    __module__ = "jupyter"

                    def __init__(self):
                        class Hook(object):
                            def register(self, what, where):
                                pass
                        self.events = Hook()

                    def register_magics(self, magic):
                        pass
                return Jupyter()
            wandb.get_ipython = get_ipython
        # no i/o wrapping - it breaks pytest
        os.environ['WANDB_MODE'] = 'clirun'
        if not request.node.get_marker('unconfigured'):
            os.environ['WANDB_API_KEY'] = 'test'
            os.environ['WANDB_ENTITY'] = 'test'
            os.environ['WANDB_PROJECT'] = 'unit-test-project'
        os.environ['WANDB_RUN_DIR'] = str(tmpdir)

        assert wandb.run is None
        assert wandb.config is None
        orig_namespace = vars(wandb)

        if request.node.get_marker('args'):
            kwargs = request.node.get_marker('args').kwargs
            # Unfortunate to enable the test to work
            if kwargs.get("dir"):
                del os.environ['WANDB_RUN_DIR']
            if kwargs.get("error"):
                err = kwargs["error"]
                del kwargs['error']

                if err == "io":
                    @classmethod
                    def error(cls):
                        raise IOError
                    monkeypatch.setattr(
                        'wandb.wandb_run.Run.from_environment_or_defaults', error)
                elif err == "socket":
                    class Error(object):
                        def listen(self, secs):
                            return False, None
                    monkeypatch.setattr("wandb.wandb_socket.Server", Error)
        else:
            kwargs = {}
        try:
            run = wandb.init(**kwargs)
            upload_logs(request_mocker, run)
            assert run is wandb.run
            assert run.config is wandb.config
        except wandb.LaunchError as e:
            run = e
        yield run

        wandb.uninit()
        assert vars(wandb) == orig_namespace
    finally:
            # restore the original environment
        os.environ.clear()
        os.environ.update(orig_environ)
