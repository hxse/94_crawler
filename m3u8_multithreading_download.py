#!/usr/bin/env python3
# coding: utf-8
from ast import Try
import grequests
import requests
import m3u8
from pathlib import Path
import subprocess
import fire

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.97 Safari/537.36",
}
http_proxy = "http://127.0.0.1:7890"
proxies = {
    "http": http_proxy,
    "https": http_proxy,
}

timeout = 60
size = 10


def createDir(path):
    dirPath = Path(".") / path
    dirPath.mkdir(parents=True, exist_ok=True)
    return dirPath


def is_file(filePath):
    isSkip = False
    if Path(filePath).exists():
        size = Path(filePath).stat().st_size
        if size > 0:
            isSkip = True
    return [filePath, isSkip]


def getTsList(m3u8file):
    m3u8obj = m3u8.loads(m3u8file)
    return ["" + i for i in m3u8obj.files]


def getCachePath(cacheDirPath, url):
    return cacheDirPath / url.split("/")[-1]


def m3u8_multithreading_download(url, fileName, cacheDirName="cache_files"):
    response = requests.get(url, headers=headers, proxies=proxies, timeout=timeout)

    if response.status_code != 200:
        print("请求失败:", response.status_code, url)
        return

    urlParent = url.split("?")[0].rsplit("/", 1)[0]
    tsNameArr = getTsList(response.text)
    tsUrlArrFull = [urlParent + "/" + i for i in tsNameArr]
    cacheDirPath = createDir(f"{cacheDirName}/{fileName}")
    tsFileArr = [(cacheDirPath / i) for i in tsNameArr]

    tsUrlArr = [  # 已下载的话则去重
        tsUrl
        for tsUrl in tsUrlArrFull
        if not is_file(getCachePath(cacheDirPath, tsUrl))[1]
    ]
    print("ts缓存已跳过", len(tsUrlArrFull) - len(tsUrlArr), "剩余", len(tsUrlArr))
    reqs = (
        grequests.get(tsUrl, headers=headers, proxies=proxies, timeout=timeout)
        for tsUrl in tsUrlArr
    )
    count = len(tsUrlArr)
    num = 0
    for res in grequests.imap(reqs, size=size):
        with open(getCachePath(cacheDirPath, res.url), "wb") as f:
            f.write(res.content)
        num += 1
        print(f"{num}/{count} {getCachePath(cacheDirPath,res.url).name}")
    ts_merge(tsFileArr, fileName)
    delete(tsFileArr, cacheDirPath)


def ts_merge(tsFileArr, output):
    tsCmd = "|".join([str(i) for i in tsFileArr])
    command = f'ffmpeg -y -nostdin -i "concat:{tsCmd}" -c copy "{output}"'
    subprocess.call(command, shell=True)


def delete(tsFileArr, cacheDirPath=False):
    for i in tsFileArr:
        i.unlink()
    if cacheDirPath:
        cacheDirPath.rmdir()
        for i in [i for i in cacheDirPath.parents][:-1]:
            try:
                i.rmdir()
            except OSError as e:
                print("无法删除:", i, e)


if __name__ == "__main__":
    url = "https://cdnt.jiuse.cloud/hls/629658/index.m3u8?t=1650619324&m=N7llU_Ps2K8GmxSyX4Bm6Q"
    fire.Fire(m3u8_multithreading_download)
