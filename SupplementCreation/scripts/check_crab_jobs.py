import argparse
import os
import re
import shutil
import subprocess
import sys

EOS_SUPPLEMENTS_DIR = "/store/user/lnestor/supplements"
EOS_REDIRECTOR = "root://cmseos.fnal.gov"
MAX_JOBS_PER_SUBDIR = 1000


def get_crab_dirs(crab_projects_dir):
    return sorted(
        os.path.join(crab_projects_dir, d)
        for d in os.listdir(crab_projects_dir)
        if os.path.isdir(os.path.join(crab_projects_dir, d))
    )


def get_job_states(crab_dir):
    """Run crab status and return {state: (pct, count, total)} from the
    'Jobs status:' block. CRAB prints the first state on that line and any
    remaining states on unlabeled continuation lines until a blank line."""
    result = subprocess.run(
        ["crab", "status", "-d", crab_dir], capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"  ERROR: crab status failed:\n{result.stderr.strip()}")
        return None

    states = {}
    in_block = False
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith("Jobs status:"):
            in_block = True
            stripped = stripped[len("Jobs status:"):].strip()
        elif in_block and not stripped:
            break
        elif not in_block:
            continue

        match = re.match(r"([A-Za-z]+)\s+([\d.]+)%\s*\(\s*(\d+)\s*/\s*(\d+)\s*\)", stripped)
        if match:
            state, pct, count, total = match.groups()
            states[state] = (float(pct), int(count), int(total))

    if not states:
        print(f"  WARNING: could not parse 'Jobs status:' block from crab status output:\n{result.stdout}")
        return None
    return states


def is_fully_finished(states):
    if len(states) != 1 or "finished" not in states:
        return False
    pct, _count, _total = states["finished"]
    return pct == 100.0


def get_output_dir(crab_dir):
    """Run crab getoutput --dump for job 1 and return the parent directory
    of its LFN (all job output files share this parent as long as the task
    has fewer than MAX_JOBS_PER_SUBDIR jobs)."""
    result = subprocess.run(
        ["crab", "getoutput", "-d", crab_dir, "--dump", "--jobids", "1"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"  ERROR: crab getoutput failed:\n{result.stderr.strip()}")
        return None

    for line in result.stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith("LFN:"):
            lfn = stripped[len("LFN:"):].strip()
            return os.path.dirname(lfn)

    print(f"  ERROR: no LFN found in crab getoutput output:\n{result.stdout}")
    return None


def dest_name_for(crab_dir):
    request_name = os.path.basename(crab_dir.rstrip("/"))
    if request_name.startswith("crab_"):
        request_name = request_name[len("crab_"):]
    return re.sub(r"_supplement_v\d+$", "", request_name)


def eos_dir_exists(eos_dir):
    result = subprocess.run(["xrdfs", EOS_REDIRECTOR, "ls", eos_dir], capture_output=True, text=True)
    return result.returncode == 0


def try_remove(dest_dir, dry_run):
    if eos_dir_exists(dest_dir):
        if dry_run:
            print(f"  [dry-run] Destination exists, would remove.")
        else:
            print(f"  Destination exists, removing.")
            result = subprocess.run(["eos", EOS_REDIRECTOR, "rm", "-r", dest_dir], capture_output=True, text=True)
            if result.returncode != 0:
                print(f"  ERROR: eos rm failed:\n{result.stderr.strip()}")
                return False

    return True


def transfer(source_dir, dest_dir, dry_run):
    if dry_run:
        print("  [dry-run] Would move crab output directory.")
    else:
        print("  Moving crab output directory.")
        result = subprocess.run(["eos", EOS_REDIRECTOR, "mv", source_dir, dest_dir], capture_output=True, text=True)
        if result.returncode != 0:
            print(f"  ERROR: eos mv failed:\n{result.stderr.strip()}")
            return False

    return True


def get_dataset_for(crab_dir, configs_dir):
    request_name = os.path.basename(crab_dir.rstrip("/"))
    if request_name.startswith("crab_"):
        request_name = request_name[len("crab_"):]

    cfg_path = os.path.join(configs_dir, f"{request_name}_cfg.py")
    if not os.path.exists(cfg_path):
        print(f"  ERROR: crab config not found at {cfg_path}")
        return None

    with open(cfg_path) as f:
        text = f.read()

    match = re.search(r"config\.Data\.inputDataset\s*=\s*['\"]([^'\"]+)['\"]", text)
    if not match:
        print(f"  ERROR: could not find inputDataset in {cfg_path}")
        return None

    return match.group(1)


def reorder_and_transfer(source_dir, dest_dir, dataset, dry_run):
    if dry_run:
        print("  [dry-run] Would reorder and transfer supplement files.")
        return True

    print("  Reordering and transferring supplement files.")
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reshuffle_supplements.py")
    result = subprocess.run([
        sys.executable, script,
        "--source-dir", source_dir,
        "--dest-dir", dest_dir,
        "--dataset", dataset,
    ])
    if result.returncode != 0:
        return False

    print("  Removing raw crab output directory.")
    result = subprocess.run(["eos", EOS_REDIRECTOR, "rm", "-r", source_dir], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ERROR: eos rm failed:\n{result.stderr.strip()}")
        return False

    return True


def cleanup(crab_dir, dry_run):
    if dry_run:
        print("  [dry-run] Would remove crab project directory.")
    else:
        print("  Removing crab project directory.")
        shutil.rmtree(crab_dir)

    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--crab-projects-dir", default="../test/crab_projects")
    parser.add_argument("--supplements-dir", default=EOS_SUPPLEMENTS_DIR)
    parser.add_argument("--dry-run", action="store_true", help="Print actions without moving or deleting anything")
    parser.add_argument("--reverse", action="store_true", help="Reverse the order crab projects are checked")
    parser.add_argument("--reorder", action="store_true", help="Reorder the lumis into files that match a central NanoAOD dataset")
    args = parser.parse_args()

    configs_dir = os.path.dirname(os.path.normpath(args.crab_projects_dir))

    crab_dirs = get_crab_dirs(args.crab_projects_dir)
    print(f"Found {len(crab_dirs)} crab project directories in {args.crab_projects_dir}")

    if args.reverse:
        crab_dirs = crab_dirs[::-1]

    transferred, not_finished, needs_manual, errors = [], [], [], []

    for crab_dir in crab_dirs:
        print(f"\n{crab_dir}")
        states = get_job_states(crab_dir)
        if states is None:
            errors.append(crab_dir)
            continue

        for state, (pct, count, total) in states.items():
            print(f"  {state}: {pct}% ({count}/{total})")

        dest_dir = os.path.join(args.supplements_dir, dest_name_for(crab_dir))
        if not try_remove(dest_dir, args.dry_run):
            errors.append(crab_dir)
            continue

        if not is_fully_finished(states):
            not_finished.append(crab_dir)
            continue

        total_jobs = next(iter(states.values()))[2]
        if total_jobs >= MAX_JOBS_PER_SUBDIR:
            print(f"  WARNING: {total_jobs} jobs >= {MAX_JOBS_PER_SUBDIR}, output likely spans multiple "
                  f"subdirectories (0000, 0001, ...) -- handle this task manually")
            needs_manual.append(crab_dir)
            continue

        source_dir = get_output_dir(crab_dir)
        if source_dir is None:
            errors.append(crab_dir)
            continue

        dest_dir = os.path.join(args.supplements_dir, dest_name_for(crab_dir))
        if not try_remove(dest_dir, args.dry_run):
            errors.append(crab_dir)
            continue


        if args.reorder:
            dataset = get_dataset_for(crab_dir, configs_dir)
            if dataset is None:
                errors.append(crab_dir)
                continue
            if not reorder_and_transfer(source_dir, dest_dir, dataset, args.dry_run):
                errors.append(crab_dir)
                continue
        else:
            if not transfer(source_dir, dest_dir, args.dry_run):
                errors.append(crab_dir)
                continue

        cleanup(crab_dir, args.dry_run)
        transferred.append(crab_dir)

    print("\n--- Summary ---")
    print(f"Transferred: {len(transferred)}")
    print(f"Not finished yet: {len(not_finished)}")
    print(f"Needs manual handling (>= {MAX_JOBS_PER_SUBDIR} jobs): {len(needs_manual)}")
    print(f"Errors: {len(errors)}")
    for crab_dir in needs_manual + errors:
        print(f"  {crab_dir}")

    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
