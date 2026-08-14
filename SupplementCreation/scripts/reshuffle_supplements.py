import argparse
import json
import os
import subprocess
import sys
import time
from array import array
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

import numpy as np
import ROOT
from tqdm import tqdm


TREEPATH = "supplementTree/Events"
EOS_REDIRECTOR = "root://cmseos.fnal.gov"


def get_root_files(eos_dir):
    result = subprocess.run(["xrdfs", EOS_REDIRECTOR, "ls", "-R", eos_dir], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ERROR: xrdfs ls -R failed:\n{result.stderr.strip()}")
        sys.exit(1)
    return [f"{EOS_REDIRECTOR}/{line.strip()}" for line in result.stdout.splitlines() if line.strip().endswith(".root")]


def make_remote_dir(eos_dir):
    result = subprocess.run(["xrdfs", EOS_REDIRECTOR, "mkdir", "-p", eos_dir], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ERROR: xrdfs mkdir -p failed:\n{result.stderr.strip()}")
        sys.exit(1)


def make_key(runs, lumis):
    return np.rec.fromarrays(
        [np.array(runs, dtype=np.int64), np.array(lumis, dtype=np.int64)],
        names="run,luminosityBlock",
    )


def read_supplement_lumis(files):
    file_lumis = {}
    supp_lumis_to_file = {}
    for path in tqdm(files, desc="Reading supplement lumis"):
        try:
            arrays = ROOT.RDataFrame(TREEPATH, path).AsNumpy(["run", "luminosityBlock"])
            runs = np.asarray(arrays["run"])
            lumis = np.asarray(arrays["luminosityBlock"])
        except Exception as e:
            print(f"ERROR reading {path}: {e}")
            continue

        file_lumis[path] = (runs, lumis)
        for run_lumi in set(zip(runs.tolist(), lumis.tolist())):
            if run_lumi in supp_lumis_to_file and supp_lumis_to_file[run_lumi] != path:
                run, lumi = run_lumi
                print(f"ERROR: run {run}, lumi {lumi} found in both {supp_lumis_to_file[run_lumi]} and {path}")
                sys.exit(1)
            supp_lumis_to_file[run_lumi] = path

    return file_lumis, supp_lumis_to_file


def get_central_runs_lumis(dataset, runs):
    def _get_central_run_one(dataset, run, retries=3, delay=5):
        for attempt in range(1, retries + 1):
            result = subprocess.run(
                ["dasgoclient", "-query", f"file,lumi dataset={dataset} run={run}", "-json"],
                capture_output=True, text=True,
            )
            if result.returncode == 0:
                break
            print(f"WARNING: dasgoclient query failed for run {run} (attempt {attempt}/{retries}): {result.stderr.strip()}")
            if attempt < retries:
                time.sleep(delay)
        else:
            print(f"ERROR: dasgoclient query failed for run {run} after {retries} attempts")
            sys.exit(1)

        files = {}
        for record in json.loads(result.stdout):
            file = record["file"][0]["name"]
            run_lumis = [(run, lumi) for lumi in record["lumi"][0]["number"]]
            files.setdefault(file, []).extend(run_lumis)
        return files

    index = {}
    sorted_runs = sorted(runs)
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(tqdm(
            executor.map(lambda run: _get_central_run_one(dataset, run), sorted_runs),
            total=len(sorted_runs), desc="Reading central lumis",
        ))
    for files in results:
        for file, run_lumis in files.items():
            index.setdefault(file, []).extend(run_lumis)
    return index


def write_runs_tree(directory, runs, version):
    directory.cd()
    tree = ROOT.TTree("Runs", "Run-level metadata")
    run_val = array("I", [0])
    version_val = array("i", [0])
    tree.Branch("run", run_val, "run/i")
    tree.Branch("version", version_val, "version/I")
    for r in runs:
        run_val[0] = r
        version_val[0] = version
        tree.Fill()
    tree.Write()


def read_version(path):
    tf = ROOT.TFile.Open(path)
    runs_tree = tf.Get("supplementTree/Runs")
    version_val = array("i", [0])
    runs_tree.SetBranchAddress("version", version_val)
    runs_tree.GetEntry(0)
    version = version_val[0]
    tf.Close()
    return version


def copy_matched_entries(needed_files, target, file_lumis):
    """Select matching entries from each needed supplement file via a TChain
    and a single CopyTree() call, instead of copying each file separately and
    merging: repeated TTree.Merge() calls leak memory (a ROOT-internal leak,
    independent of PyROOT object ownership) and grow unbounded over a long
    run."""
    chain = ROOT.TChain(TREEPATH)
    combined = ROOT.TEntryList()
    n_matched_files = 0
    for supp_file in needed_files:
        runs, lumis = file_lumis[supp_file]
        idx = np.flatnonzero(np.isin(make_key(runs, lumis), target))
        if len(idx) == 0:
            continue

        chain.Add(supp_file)
        sub = ROOT.TEntryList("", "", TREEPATH, supp_file)
        for i in idx:
            sub.Enter(int(i))
        combined.Add(sub)
        n_matched_files += 1

    if n_matched_files == 0:
        return None

    chain.SetEntryList(combined)
    final_tree = chain.CopyTree("")
    ROOT.SetOwnership(final_tree, True)
    final_tree.SetDirectory(0)
    return final_tree


# Set by reshuffle() before the process pool is created, and inherited by
# each forked worker via copy-on-write -- passing file_lumis/supp_lumis_to_file
# as submit()/map() arguments instead would pickle and ship the whole (multi-GB)
# index to every worker.
_supp_lumis_to_file = None
_file_lumis = None
_dest_dir = None
_version = None


def _reshuffle_one(central_file_and_lumis):
    central_file, lumis = central_file_and_lumis
    central_lumis = sorted(set(tuple(l) for l in lumis))
    needed = sorted({_supp_lumis_to_file[l] for l in central_lumis if l in _supp_lumis_to_file})

    if not needed:
        return "empty", 0

    target_runs, target_lumis = zip(*central_lumis)
    target = make_key(target_runs, target_lumis)

    final_tree = copy_matched_entries(needed, target, _file_lumis)

    if final_tree is None:
        return "empty", 0

    output_path = f"{_dest_dir.rstrip('/')}/{os.path.basename(central_file)}"
    out = ROOT.TFile.Open(f"{EOS_REDIRECTOR}/{output_path}", "RECREATE")
    subdir = out.mkdir("supplementTree")
    subdir.cd()

    n = final_tree.GetEntries()
    final_tree.Write()
    write_runs_tree(subdir, sorted(set(target_runs)), _version)
    out.Close()
    del final_tree

    return "written", n


def reshuffle(central_file_to_lumis, supp_lumis_to_file, file_lumis, dest_dir, version, n_workers=4):
    global _supp_lumis_to_file, _file_lumis, _dest_dir, _version
    _supp_lumis_to_file = supp_lumis_to_file
    _file_lumis = file_lumis
    _dest_dir = dest_dir
    _version = version

    n_written = 0
    n_empty = 0
    n_events = 0

    items = list(central_file_to_lumis.items())
    with ProcessPoolExecutor(max_workers=n_workers) as executor:
        for status, n in tqdm(executor.map(_reshuffle_one, items), total=len(items), desc="Reshuffling"):
            if status == "empty":
                n_empty += 1
            else:
                n_written += 1
                n_events += n

    print(f"\nWrote {n_written} reshuffled files ({n_events} events total)")
    print(f"{n_empty} central files had no supplement coverage (left with no output file)")


def main():
    parser = argparse.ArgumentParser(
        description="Reshuffle existing per-CRAB-job supplement files into one "
                     "file per central NanoAOD file, so analysis-time reads "
                     "become 1:1 with central files instead of redundantly "
                     "re-reading shared supplement files. Run inside the "
                     "CMSSW environment (`eval `scramv1 runtime -sh``)."
    )
    parser.add_argument("--dataset", required=True, help="The central NanoAOD DAS dataset")
    parser.add_argument("--source-dir", required=True, help="EOS xrootd directory containing the existing supplement files")
    parser.add_argument("--dest-dir", required=True, help="EOS xrootd directory to write the reshuffled supplement files into")
    parser.add_argument("--limit", type=int, help="Debug: only reshuffle the first N central files")
    parser.add_argument("--workers", type=int, default=8, help="Number of parallel worker processes for reshuffling")
    args = parser.parse_args()

    files = get_root_files(args.source_dir)
    if not files:
        print("ERROR: no supplement files found")
        sys.exit(1)
    print(f"Found {len(files)} supplement files")

    version = read_version(files[0])

    file_lumis, supp_lumis_to_file = read_supplement_lumis(files)
    print(f"Found {len(supp_lumis_to_file)} unique run/lumi pairs")

    print("Reading run/lumis of central files via dasgoclient...")
    runs = {run for run, _ in supp_lumis_to_file}
    central_file_to_lumis = get_central_runs_lumis(args.dataset, runs)
    print(f"Found {len(central_file_to_lumis)} central files")

    if args.limit:
        central_file_to_lumis = dict(list(central_file_to_lumis.items())[:args.limit])
        print(f"--limit given: only reshuffling the first {len(central_file_to_lumis)} central files")

    make_remote_dir(args.dest_dir)
    reshuffle(central_file_to_lumis, supp_lumis_to_file, file_lumis, args.dest_dir, version, n_workers=args.workers)


if __name__ == "__main__":
    main()
