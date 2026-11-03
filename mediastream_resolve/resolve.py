"""Resolve side of the Mediastream tool, behind one small interface.

An adapter offers: presets() -> [str]; import_media(paths) -> bool;
render_current(job_args, timeout) -> output file path. Failures raise ResolveError.
ScriptAdapter talks to Resolve's scripting API directly (standalone package);
the MCP server passes its own adapter so it keeps its extra render safety checks.
"""
import os
import sys
import time


class ResolveError(RuntimeError):
    def __init__(self, message, code="RESOLVE_ERROR"):
        super().__init__(message)
        self.code = code


def _completed(st):
    """Locale-independent: JobStatus is localized, so trust CompletionPercentage / Error."""
    st = st or {}
    if st.get("JobStatus") == "Complete":
        return True
    if st.get("Error"):
        return False
    try:
        return float(st.get("CompletionPercentage")) >= 100
    except (TypeError, ValueError):
        return False


class ScriptAdapter:
    API = {"darwin": "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting",
           "win32": os.path.expandvars(r"%PROGRAMDATA%\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting"),
           }.get(sys.platform, "/opt/resolve/Developer/Scripting")

    def _project(self):
        api = os.environ.get("RESOLVE_SCRIPT_API", self.API)
        sys.path.append(os.path.join(api, "Modules"))
        try:
            import DaVinciResolveScript as dvr
        except ImportError:
            raise ResolveError("DaVinciResolveScript not found: is DaVinci Resolve installed?",
                               "NO_RESOLVE_API") from None
        resolve = dvr.scriptapp("Resolve")
        proj = resolve and resolve.GetProjectManager().GetCurrentProject()
        if not proj:
            raise ResolveError("Resolve is not reachable or has no open project "
                               "(Preferences > General > External scripting using: Local).",
                               "NO_PROJECT")
        return proj

    def presets(self):
        return self._project().GetRenderPresetList() or []

    def import_media(self, paths):
        mp = self._project().GetMediaPool()
        if not mp:
            raise ResolveError("Failed to get MediaPool", "NO_MEDIA_POOL")
        return bool(mp.ImportMedia(list(paths)))

    supports_progress = True

    def render_current(self, job, timeout=3600, progress=None):
        proj = self._project()
        if not proj.GetCurrentTimeline():
            raise ResolveError("No current timeline", "NO_CURRENT_TIMELINE")
        if not os.path.isdir(job.get("target_dir") or ""):
            raise ResolveError("target_dir does not exist: %s" % job.get("target_dir"), "RENDER_JOB_FAILED")
        if job.get("from_preset") and not proj.LoadRenderPreset(job["from_preset"]):
            raise ResolveError("could not queue render job: unknown preset", "RENDER_JOB_FAILED")
        settings = dict(job.get("settings") or {}, TargetDir=job["target_dir"])
        if job.get("custom_name"):
            settings["CustomName"] = job["custom_name"]
        job_id = proj.SetRenderSettings(settings) and proj.AddRenderJob()
        if not job_id:
            raise ResolveError("could not queue render job", "RENDER_JOB_FAILED")
        if not proj.StartRendering([job_id]):
            raise ResolveError("render did not start", "RENDER_START_FAILED")
        deadline = time.time() + float(timeout)
        while time.time() < deadline:
            st = proj.GetRenderJobStatus(job_id) or {}
            if progress and isinstance(st.get("CompletionPercentage"), (int, float)):
                progress("render", st["CompletionPercentage"], 100)
            if _completed(st):
                break
            if st.get("Error"):
                raise ResolveError("render failed: %s" % st["Error"], "RENDER_FAILED")
            time.sleep(3)
        else:
            raise ResolveError("render timed out", "RENDER_TIMEOUT")
        j = next((x for x in proj.GetRenderJobList() or [] if x.get("JobId") == job_id), {})
        out = os.path.join(j.get("TargetDir") or "", j.get("OutputFilename") or "")
        # ponytail: only checks the file exists and is non-empty; the MCP adapter also catches
        # Complete-but-blank renders (issue #164). Port that check if blank uploads show up.
        if not (j.get("OutputFilename") and os.path.isfile(out) and os.path.getsize(out) > 0):
            raise ResolveError("render output failed verification; not uploading", "RENDER_UNVERIFIED")
        return out
