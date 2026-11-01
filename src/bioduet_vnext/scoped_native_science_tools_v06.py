"""Authorization adapters around unchanged official tool executors/schemas."""
def register_scoped_native_tools(gate):
    from openhands.sdk.tool.registry import register_tool
    from openhands.sdk.tool import ToolExecutor
    from openhands.tools.terminal.definition import TerminalTool,TerminalObservation
    from openhands.tools.file_editor.definition import FileEditorTool
    from .science_execution_gate_v05 import PendingScientificExecution,ScientificGateIntegrityError
    class GuardedExecutor(ToolExecutor):
        def __init__(self,delegate,kind):self.delegate=delegate;self.kind=kind;self.science_gate=gate
        def __call__(self,action,conversation=None):
            if self.kind=="file":
                gate.view_path(action.path,action.command!="view")
                return self.delegate(action,conversation)
            try:permit=gate.authorize(action)
            except PendingScientificExecution as e:
                return TerminalObservation.from_text(str(e),is_error=True,command=action.command,exit_code=None)
            except Exception:
                gate.poisoned=True
                if conversation is not None:conversation.pause()
                raise
            try:
                observation=self.delegate(action,conversation);gate.observed(permit,observation);return observation
            except Exception:
                gate.poisoned=True
                if conversation is not None:conversation.pause()
                raise
        def close(self):self.delegate.close()
    class TerminalFactory(TerminalTool):
        @classmethod
        def create(cls,conv_state,**kwargs):
            definitions=TerminalTool.create(conv_state,**kwargs)
            return [definition.model_copy(update={"executor":GuardedExecutor(definition.executor,"terminal"),"description":definition.description+'\nScientific fit requires an actual frozen-code scope check and current Root execution receipt; unreviewed commands/stdin are blocked. Register your actual code/dependencies/options/input strategy and wait for current permitted immutable command. No method or solution is supplied by this gate.'}) for definition in definitions]
    class FileFactory(FileEditorTool):
        @classmethod
        def create(cls,conv_state,**kwargs):
            definitions=FileEditorTool.create(conv_state,**kwargs)
            return [definition.model_copy(update={"executor":GuardedExecutor(definition.executor,"file")}) for definition in definitions]
    register_tool("TerminalTool",TerminalFactory);register_tool("FileEditorTool",FileFactory)
