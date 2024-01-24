#!/usr/bin/python3
import logging
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import requests

CONFIG = {
    "LOG_DIRECTORY": "logs",
    "LOGFILE_EXTENSION": ".log.txt",
    "LOGFILE_LIMIT": 5,
    "DOWNLOAD_CHUCK_SIZE_MiB": 10,
}


@dataclass(frozen=True)
class UpdateData:
    url: str = requests.head(
        f"https://discord.com/api/download?platform=linux&format=deb",
        allow_redirects=True
    ).url
    version: str = url.split("/")[5]

    def generate_download_path(self):
        return Path(self.url.split("/")[6]).resolve()

    def download(
            self,
            path: Path = None,
            chunk_size=CONFIG["DOWNLOAD_CHUCK_SIZE_MiB"] * 1024 * 1024
    ) -> Path:
        if path is None:
            path = self.generate_download_path()

        response = requests.get(self.url, stream=True)
        total_size = int(response.headers.get("content-length", 0))
        downloaded_size = 0

        with path.open("wb") as file:
            for chunk in response.iter_content(chunk_size):
                file.write(chunk)
                downloaded_size += len(chunk)
                logging.info(
                    f"Download Progress: {downloaded_size} B / {total_size} B | "
                    f"{(downloaded_size / total_size) * 100:.2f}%"
                )

        return path


def get_current_installed_version() -> str:
    package_status = subprocess.run(
        ["dpkg", "-s", "discord"],
        capture_output=True,
        text=True
    ).stdout.split("\n")
    for item in package_status:
        if item.startswith("Version"):
            return item.split(" ")[1]


def remove_old_logs(
        log_directory: Path = Path(CONFIG["LOG_DIRECTORY"]).resolve(),
        limit: int = CONFIG["LOGFILE_LIMIT"]
):
    if limit < 0:
        logging.info("No limit set - No logs deleted")
        return
    logging.info(f"Searching for old logs in {log_directory}")

    logfiles = sorted(log_directory.glob(f"*{CONFIG["LOGFILE_EXTENSION"]}"), key=str, reverse=True)
    logging.info(f"Logfiles: {logfiles}")

    while len(logfiles) > limit:
        file = logfiles.pop()
        logging.info(f"Trying to delete {file}")
        file.unlink()
        if not file.exists():
            logging.info(f"Deleted {file}")


def main():
    start_timestamp = datetime.now()

    log_directory = Path(CONFIG["LOG_DIRECTORY"]).resolve()
    logging.basicConfig(
        filename=str(
            (log_directory / Path(
                f"discord-updater-{start_timestamp.strftime('%y-%m-%d-%H-%M-%S')}{CONFIG['LOGFILE_EXTENSION']}")).resolve()
        ),
        filemode="w",
        level=logging.INFO
    )
    logging.getLogger().addHandler(logging.StreamHandler(sys.stdout))

    try:
        logging.info(f"Process started at {start_timestamp}")

        installed_version = get_current_installed_version()
        logging.info(f"Currently Installed: Version {installed_version}")

        logging.info("Looking for update")
        update_data = UpdateData()
        logging.info(f"Newest: Version {update_data.version}")

        if installed_version == update_data.version:
            logging.info("Installed version up to date")
            return

        filepath = update_data.generate_download_path()

        logging.info(f"Downloading {update_data.url}")
        filepath = update_data.download(filepath)
        logging.info(f"Downloaded {update_data.url}")

        logging.info(f"Installing {filepath} with apt-get")
        try:
            out = subprocess.run(["apt-get", "install", "-y", str(filepath)], check=True, capture_output=True,
                                 text=True)
            logging.info(f"stdout: {out.stdout}")
        except subprocess.CalledProcessError as exception:
            logging.exception(str(exception))
            logging.info(f"stdout: {exception.stdout}")
            logging.info(f"stderr: {exception.stderr}")
            raise exception
        finally:
            logging.info(f"Deleting {filepath}")
            filepath.unlink()
            logging.info(f"Deleted {filepath}")
    finally:
        logging.info("Searching for old logs")
        remove_old_logs()
        logging.info("Done searching for old logs")
        logging.info(f"Process ended at {datetime.now()}")


if __name__ == '__main__':
    try:
        main()
    except BaseException as e:
        logging.exception(e)
        raise e
