"""Finite zero-science R runtime qualifier, admitted separately within main I6.
Only fixed version/load reporting is executed. No counts, fit, filtering, DE,
reference analysis, provider/model or original historical-env execution.
"""
import argparse,json,os,subprocess,hashlib,time,math
from pathlib import Path
PROGRAM = r'''
args <- commandArgs(trailingOnly=TRUE)
stopifnot(length(args)==3)
.libPaths(c(args[[1]], .Library))
wanted <- c(edgeR="4.4.2",limma="3.62.2",locfit="1.5-9.10",statmod="1.5.0")
for (p in names(wanted)) {
 suppressPackageStartupMessages(library(p,character.only=TRUE))
 stopifnot(packageVersion(p)==package_version(wanted[[p]]))
 cat("PACKAGE_VERSION\t",p,"\t",as.character(packageVersion(p)),"\n",sep="")
}
cat("R_VERSION\t",as.character(getRversion()),"\n",sep="")
for (p in .libPaths()) cat("LIB_PATH\t",p,"\n",sep="")
dlls <- getLoadedDLLs()
for (name in names(dlls)) cat("LOADED_DLL\t",name,"\t",dlls[[name]][["path"]],"\n",sep="")
writeLines("RUNTIME_LOAD_READY_NO_SCIENCE",args[[2]])
started <- proc.time()[["elapsed"]]
while (!file.exists(args[[3]]) && proc.time()[["elapsed"]]-started<15) Sys.sleep(0.05)
stopifnot(file.exists(args[[3]]))
'''
def main():
    ap=argparse.ArgumentParser();ap.add_argument("--proof",required=True);ap.add_argument("--proof-sha256",required=True)
    args=ap.parse_args();raw=Path(args.proof).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=args.proof_sha256:raise ValueError("ROOT_RUNTIME_PROOF_SHA")
    proof=json.loads(raw)
    if proof["schema"]!="bioduet-root-staged-R-runtime-qualification/1" or proof["source_kind"]!="runtime_qualification_no_scientific_data":
        raise ValueError("NEW_ZERO_SCIENCE_RUNTIME_SCOPE")
    if os.getuid()!=1008 or os.getgroups()!=[]:raise ValueError("ROOT_DROPPED_PROCESS")
    if proof["staged_bytes_accepted_for_qualification_only"] is not True or proof["counts_or_dataset_mounted"] is not False:
        raise ValueError("P_STAGED_BYTES_AND_NO_DATA_ONLY")
    timeout=min(60,proof["deadline_monotonic"]-time.monotonic())
    if not math.isfinite(timeout) or timeout<=0:raise ValueError("FINITE_CURRENT_RUNTIME_SCOPE")
    out=Path(proof["output_root"]);out.mkdir(mode=0o700)
    env={k:proof["clean_environment"][k] for k in proof["clean_environment"]}
    # No inheritance of HOME/provider credentials/private environments.
    for k in ("R_ENVIRON","R_ENVIRON_USER","R_PROFILE","R_PROFILE_USER"):
        if env.get(k)!=proof["Root_empty_readonly_file"]:raise ValueError("FIXED_EMPTY_STARTUP")
    if any(env.get(k)!="1" for k in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS")):
        raise ValueError("FROZEN_COMMON_ENV_RESOURCE_THREADS")
    command=[proof["staged_Rscript_namespace_path"],"--vanilla","-e",PROGRAM,
             proof["readonly_existing131_library_namespace_path"],str(out/"runtime-load-ready"),
             proof["Root_runtime_mapping_capture_ACK_path"]]
    # Only Root can admit this exact R/ELF/loader descendant tree and its IO.
    child=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE,cwd=out,env=env)
    try:stdout,stderr=child.communicate(timeout=timeout)
    except BaseException:
        child.kill();stdout,stderr=child.communicate()
        (out/"R.stdout").write_bytes(stdout);(out/"R.stderr").write_bytes(stderr)
        raise
    (out/"R.stdout").write_bytes(stdout);(out/"R.stderr").write_bytes(stderr)
    report={"schema":"bioduet-R-runtime-qualification-observation/1","parent_wait_status":child.returncode,
        "stdout_bytes":len(stdout),"stdout_sha256":hashlib.sha256(stdout).hexdigest(),
        "stderr_bytes":len(stderr),"stderr_sha256":hashlib.sha256(stderr).hexdigest(),
        "R_PROGRAM_sha256":hashlib.sha256(PROGRAM.encode()).hexdigest(),
        "actual_DLL_and_all_descendant_trace_join_requires_Root":True,
        "all_descendant_retirement_inferred_from_parent_wait":False,"scientific_analysis_runs":0,
        "models":0,"scope":"fixed runtime/library load only; no scientific validity"}
    data=(json.dumps(report,sort_keys=True,indent=2)+"\n").encode();(out/"observation.json").write_bytes(data)
    if child.returncode!=0:raise RuntimeError("R_RUNTIME_LOAD_QUALIFICATION_FAILED")
if __name__=="__main__":main()
