"""Compose the existing file/job/notice/authority routes into a bound participant host.
Fresh attempt filesystem only; retained jobs can be inspected with JobStore separately.
No parallel scientific world, process launcher, SDK import, network, or admission is
created here. A trusted supervisor supplies its existing authority and finite launcher.
Closing this composition closes file descriptors; it does not certify remote job death.
"""
from pathlib import Path
from .contracts_v01 import Scope,require,nonempty
from .workspace_v02 import Workspace
from .jobs_v03 import JobStore
from .jobs_v02 import JobDispatcher
from .change_notices_v03 import DurableChangeNotices
from .participant_tools_v05 import ParticipantTools
from .mcp_bridge_v02 import BoundMCP

class ParticipantSession:
    def __init__(self,root,*,episode_id,attempt_id,project_id,information_mode,scopes,
                 authorize_tool,verify_commit,authorize_notice_read,retrieval=None,datasets=None,
                 authorize_launch=None,launch=None,verify_launch=None):
        require(all(nonempty(x) for x in (episode_id,attempt_id,project_id)),"SESSION_IDENTITY")
        require(information_mode in ("change_notice","analysis_anomaly"),"INFORMATION_MODE")
        require(all(callable(x) for x in (authorize_tool,verify_commit,authorize_notice_read)),
                "TRUSTED_SESSION_CALLBACKS")
        require(type(scopes) is list and bool(scopes) and
                all(type(s) is Scope and s.role in ("A","H") and
                    (s.episode_id,s.attempt_id,s.project_id)==(episode_id,attempt_id,project_id) for s in scopes)
                and len({s.principal_id for s in scopes})==len(scopes),"SESSION_SCOPES")
        callbacks=(authorize_launch,launch,verify_launch)
        require(all(x is None for x in callbacks) or all(callable(x) for x in callbacks),
                "INCOMPLETE_EXECUTION_HOST")
        root=Path(root);require(root.is_absolute() and not root.exists() and not root.is_symlink(),
                               "FRESH_SESSION_ROOT")
        root.mkdir(mode=0o700)
        self._closed=False;self.workspace=None;self.jobs=None;self.notices=None
        self.router=None;self.dispatcher=None;self._scopes={};self._bridges={}
        self._authorize_tool=authorize_tool
        try:
            self.workspace=Workspace(root/"workspace")
            self.jobs=JobStore(root/"jobs")
            self.notices=DurableChangeNotices(root/"notices",information_mode=information_mode,
                episode_id=episode_id,attempt_id=attempt_id,project_id=project_id,
                verify_commit=verify_commit,authorize_read=authorize_notice_read)
            self.router=ParticipantTools(workspace=self.workspace,jobs=self.jobs,notices=self.notices,
                                       retrieval=retrieval,datasets=datasets,authorize=self._authorize)
            for scope in scopes:
                self.router.bind(scope);self._scopes[scope.principal_id]=scope
                self._bridges[scope.principal_id]=BoundMCP(self.router,scope)
            if launch is not None:
                self.dispatcher=JobDispatcher(jobs=self.jobs,workspace=self.workspace,
                    authorize_launch=authorize_launch,launch=launch,verify_launch=verify_launch)
        except BaseException:
            self.close();raise

    def _issued(self,scope):
        require(not self._closed and self._scopes.get(scope.principal_id) is scope,"SESSION_SCOPE")

    def _authorize(self,scope,name,args):
        self._issued(scope)
        return self._authorize_tool(scope,name,args)

    def bridge(self,scope):
        self._issued(scope);return self._bridges[scope.principal_id]

    def dispatch(self,scope,job_id):
        self._issued(scope);require(self.dispatcher is not None,"EXECUTION_HOST_UNAVAILABLE")
        return self.dispatcher.start(scope,job_id)

    def committed_change(self,recipient,event,authority_receipt):
        self._issued(recipient)
        return self.notices.committed_change(recipient,event,authority_receipt)

    def close(self):
        if getattr(self,"_closed",True):return
        self._closed=True
        for component in (self.notices,self.jobs,self.workspace):
            if component is not None:component.close()

    def __enter__(self):
        require(not self._closed,"SESSION_CLOSED");return self

    def __exit__(self,*args):
        self.close()
