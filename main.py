import os
import re
from math import floor
from pathlib import Path
from browserforge.headers import HeaderGenerator

import curl_cffi
from dotenv import load_dotenv
from pydantic import BaseModel, Field, HttpUrl
import shutil

owner = 'topjohnwu'
repo = 'Magisk'

session = curl_cffi.AsyncSession()
env_file_path = Path(__file__).parent / '.env'
if env_file_path.is_file():
    load_dotenv(env_file_path)
github_token = os.getenv("APP_GITHUB_TOKEN", os.getenv("GITHUB_TOKEN"))
assert github_token, "Unable to find github token in environment variables."

dist_path = Path(__file__).parent / "dist"
if dist_path.exists():
    shutil.rmtree(dist_path)
dist_path.mkdir(parents=False, exist_ok=False)

http_headers = {
    **HeaderGenerator().generate(),
    "Accept": "application/vnd.github+json",
    "User-Agent": "",
    "Authorization": f"Bearer {github_token}",
    "X-GitHub-Api-Version": "2022-11-28"
}

async def get_last_release():
    response = await session.get(
        f"https://api.github.com/repos/{owner}/{repo}/releases/latest",
        headers=http_headers,
    )
    assert response.status_code == 200, f"Failed to fetch releases: {response.status_code}. {response.text}"
    response = ReleaseResponse.model_validate(response.json())
    link: str =await download_apk(response)
    node: str = await download_note(response)
    print("Generating channel file...")
    channel = Channel(
        magisk=ChannelMagisk(
            version=str(get_version_number(response)),
            versionCode=str(get_version_code(response)),
            link=link,
            note=node,
        ),
        stub=ChannelStub(
            versionCode=str(get_sub_version_code(response)),
            link=link,
        )
    )
    with open(dist_path / "stable.json", 'w') as f:
        f.write(channel.model_dump_json(indent=2))


def get_version_number(response: "ReleaseResponse") -> float:
    pattern = re.compile(r"(?<=v)\d+\.\d+")
    match = pattern.search(response.tag_name)
    assert match, f"Invalid tag format: {response.tag_name}"
    first_match = match.group(0)
    result = float(first_match)
    assert result >= 0, f"Version number must be non-negative: {result}"
    return result

def get_version_code(response: "ReleaseResponse") -> int:
    return int(get_version_number(response) * 1000)

def get_sub_version_code(response: "ReleaseResponse") -> int:
    return int(floor(get_version_number(response)))

async def download_apk(response: "ReleaseResponse") -> str:
    version_number = get_version_number(response)
    asset = next((asset for asset in response.assets if str(asset.browser_download_url).endswith(".apk")), None)
    assert asset, f"Apk asset not found. Available assets: {response.assets}"
    url = str(asset.browser_download_url)
    file_path = dist_path / f"{version_number}.apk"
    if file_path.exists():
        file_path.unlink()
    print("Downloading APK from:", url)
    apk_response = await session.get(url, stream=True, headers=http_headers)
    with open(file_path, 'wb') as f:
        async for chunk in apk_response.aiter_content(chunk_size=1024):
            if chunk:
                f.write(chunk)
    return url

async def download_note(response: "ReleaseResponse") -> str:
    version_number = get_version_number(response)
    asset = next((asset for asset in response.assets if str(asset.browser_download_url).endswith(".md")), None)
    assert asset, f"Note asset not found. Available assets: {response.assets}"
    url = str(asset.browser_download_url)
    file_path = dist_path / f"{version_number}.md"
    if file_path.exists():
        file_path.unlink()
    print("Downloading Note from:", url)
    note_response = await session.get(url, stream=True, headers=http_headers)
    with open(file_path, 'wb') as f:
        async for chunk in note_response.aiter_content(chunk_size=1024):
            if chunk:
                f.write(chunk)
    return url


class ReleaseResponse(BaseModel):
    tag_name: str = Field(min_length=1, max_length=10, examples=["v29.0"])
    assets: list["ReleaseResponseAsset"] = Field(min_length=1)

class ReleaseResponseAsset(BaseModel):
    browser_download_url: HttpUrl = Field(
        min_length=1,
        max_length=1000,
        examples=[
            "https://github.com/topjohnwu/Magisk/releases/download/v29.0/Magisk-v29.0.apk",
            "https://github.com/topjohnwu/Magisk/releases/download/v29.0/notes.md",
        ],
    )

class ChannelMagisk(BaseModel):
    version: str = Field(
        min_length=1,
        pattern=r"^\d+\.\d+$",
        examples=["23.0"],
    )
    versionCode: str = Field(
        min_length=1,
        pattern=r"^\d+$",
        examples=["23000"],
    )
    link: str = Field(
        min_length=1,
        max_length=1000,
    )
    note: str = Field(
        min_length=1,
        max_length=1000,
    )

class ChannelStub(BaseModel):
    versionCode: str = Field(
        min_length=1,
        pattern=r"^\d+$",
        examples=["23"],
    )
    link: str = Field(
        min_length=1,
        max_length=1000,
    )

class Channel(BaseModel):
    magisk: ChannelMagisk
    stub: ChannelStub

if __name__ == "__main__":
    import asyncio
    asyncio.run(get_last_release())
