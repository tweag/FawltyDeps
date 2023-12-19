from PyPI_analysis.main import main
from contextlib import contextmanager
from pathlib import Path
import pandas as pd
import subprocess
import tempfile
from tqdm import tqdm

from concurrent.futures import ThreadPoolExecutor, wait


@contextmanager
def clone(source_url: str):
    d = tempfile.TemporaryDirectory()
    out = subprocess.run(
        f"git clone {source_url}.git checkout",
        shell=True,
        capture_output=True,
        cwd=d.name,
        env={
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_ASKPASS": "echo",
            "SSH_ASKPASS": "echo",
            "GCM_INTERACTIVE": "never",
        },
    )
    if out.returncode != 0:
        raise Exception(out.stderr)
    yield Path(d.name).joinpath("checkout")
    d.cleanup()


def do_analysis(repo_url: str, name: str, out_dir: Path) -> None:
    repo_url = repo_url.rstrip("/")
    try:
        with clone(repo_url) as repo:
            with open(out_dir.joinpath(f"{name}.json"), "w") as f:
                main([str(repo), "--json", "--project-name", name], stdout=f)
    except Exception as e:
        print(e)


if __name__ == "__main__":
    pypi_projects = pd.read_csv("~/Downloads/pypi-project-urls-with-meta-19122023.csv")
    pypi_projects.sort_values(by="annual_downloads", ascending=False, inplace=True)
    out_dir = Path("analysis-results")
    out_dir.mkdir(exist_ok=True)
    tasks = []
    with tqdm(
        desc="Running FawltyDeps analysis",
        total=len(pypi_projects),
        position=0,
        leave=True,
    ) as pbar:
        with ThreadPoolExecutor() as ex:
            for name, repo_url, _downloads, _keywords in pypi_projects.itertuples(
                index=False
            ):
                if not repo_url:
                    continue
                result = ex.submit(do_analysis, repo_url, name, out_dir)
                result.add_done_callback(lambda _x: pbar.update())
                tasks.append(result)
            wait(tasks)
