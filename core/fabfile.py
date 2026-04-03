# Default path to the repo on the remote (override with env REMOTE_REPO_PATH if needed)
REMOTE_REPO_PATH = "~/edge-to-core-comparative-analysis"


@task
def run_bench(c, sifi=False):
    """Run the bench normally, or with SIFI if specified."""
    sifi_val = "true" if sifi else "false"
    
    print(f"Starting iteration (SIFI={sifi_val}) on {c.host}...")
    
    # Passing the choice into the container via -e (environment variable)
    result = c.run(f"docker run --rm -e ENABLE_SIFI={sifi_val} assurance-harness", warn=True)
    
    if result.failed:
        print(f"Iteration on {c.host} failed as expected. Measuring recovery...")
        # (You can trigger your recovery logic here)
    else:
        print(f"Iteration on {c.host} completed successfully.")


@task
def run_bench_with_results(c, sifi=False):
    """Run the bench and write results into the remote repo's results/ directory."""
    sifi_val = "true" if sifi else "false"
    path = REMOTE_REPO_PATH
    abs_path = c.run(f"cd {path} && pwd", hide=True).stdout.strip()
    result = c.run(
        f"mkdir -p {path}/results && docker run --rm "
        f"-e ENABLE_SIFI={sifi_val} "
        f"-v {abs_path}/results:/app/results "
        f"assurance-harness python3 /app/core/main.py",
        warn=True,
    )
    if result.failed:
        print(f"Iteration on {c.host} failed (SIFI={sifi_val}).")
    else:
        print(f"Iteration on {c.host} completed; results in {abs_path}/results/")