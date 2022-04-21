#!/usr/bin/env python3
# coding: utf-8
from ast import parse
import grequests
from pydantic import FilePath
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import fire
from time import sleep
from pathlib import Path
import re

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.97 Safari/537.36",
}
http_proxy = "http://127.0.0.1:7890"
proxies = {
    "http": http_proxy,
    "https": http_proxy,
}

timeout = 60
size = 6


def validateName(name, target=""):
    re_str = r"[\/\\\:\*\?\"\<\>\|]"  # '/ \ : * ? " < > |'
    new_name = re.sub(re_str, target, name)
    return new_name


def createDir(path):
    dirPath = Path(".") / path
    dirPath.mkdir(parents=True, exist_ok=True)
    return dirPath


def download_m3u8(url, name):
    """
    download m3u8 url
    """
    import subprocess

    command = f'ffmpeg -y -nostdin -http_proxy {http_proxy} -i "{url}" -c copy {name}'

    res = subprocess.call(command, shell=True)
    # the method returns the exit code

    # print("Returned Value: ", res)


def parse_m3u8(text):
    soup = BeautifulSoup(text, "html.parser")
    titleEl = soup.select_one(".container-title")
    title = titleEl.text.strip()
    videoEl = soup.select_one("#video-play")
    m3u8_url = videoEl["data-src"]

    likeEl = soup.select_one(".likeBtn")
    like = likeEl.text.strip()
    dislikeEl = soup.select_one(".dislikeBtn")
    dislike = dislikeEl.text.strip()
    favoriteEl = soup.select_one(".favoriteBtn span")
    favorite = favoriteEl.text.strip()

    tabEl = soup.select_one("#videoShowTabAbout")
    authorEl = tabEl.select("div div:nth-child(1)")[-1].select_one("a")
    author = authorEl.text.strip()
    authorUrl = authorEl["href"]
    calendarEl = tabEl.select("div div:nth-child(2)")[0]
    calendar = calendarEl.text.strip()
    viewEl = tabEl.select("div div:nth-child(2)")[1]
    view = viewEl.text.strip()
    return {
        "videoTitle": title,
        "m3u8_url": m3u8_url,
        "like": like,
        "dislike": dislike,
        "favorite": favorite,
        "author": author,
        "authorUrl": authorUrl,
        "calendar": calendar,
        "view": view,
    }


def get_m3u8(urlArr):
    """
    并发解析视频下载连接
    """
    reqs = (
        grequests.get(url, headers=headers, proxies=proxies, timeout=timeout)
        for url in urlArr
    )
    resArr = grequests.map(reqs, size=size)
    return [parse_m3u8(response.text) for response in resArr]


def get_m3u8_one(url):
    """
    get m3u8 url
    """
    response = requests.get(url, headers=headers, proxies=proxies, timeout=timeout)
    if response.status_code == 200:
        return parse_m3u8(response.text)


def get_domain(url):
    return f"{urlparse(url).scheme}://{urlparse(url).hostname}"


def get_page(url, sec=0):
    """
    get all page video
    example url: https://jiuse88.com/author/91%E6%8E%A2%E8%8A%B1%E5%B0%8F%E6%BB%A1
    example url: https://jiuse88.com/author/91%E7%8A%B6%E5%85%83%E9%83%8E
    """
    dataArr = []
    firstPage = get_page_one(url + "?page=1")  # 初次获取page
    dataArr.extend(firstPage["data"])
    if firstPage["pageCount"] > 1:  # 获取后续page
        for num in range(2, firstPage["pageCount"] + 1):
            sleep(sec)
            print(f"page {num} sleep {sec} ...")
            otherPage = get_page_one(url + f"?page={num}")
            dataArr.extend(otherPage["data"])
    return dataArr


def get_page_one(url):
    """
    get one page video
    """
    filterArr = ["«", "»", "上一页", "下一页", "..."]  # 页面页码按钮过滤
    response = requests.get(url, headers=headers, proxies=proxies, timeout=timeout)
    if response.status_code == 200:
        text = response.text
        soup = BeautifulSoup(text, "html.parser")
        videoElArr = soup.select(".colVideoList .video-elem")
        data = [
            {
                "title": el.select_one(".title").text,
                "url": el.select_one(".title")["href"],
            }
            for el in videoElArr
        ]
        pageLinkArr = [
            i.text for i in soup.select(".page-link") if i.text not in filterArr
        ]
        pageCount = int(pageLinkArr[-1]) if pageLinkArr else 1
        return {"pageCount": pageCount, "data": data}


def get_file(fileName, dirName):
    fileName = validateName(f'{fileName}".mp4"', "")  # 把文件名净化成windows安全的字符
    filePath = Path(dirName) / fileName
    isSkip = False
    if Path(filePath).exists():
        size = Path(filePath).stat().st_size
        if size > 0:
            isSkip = True
    return [filePath, isSkip]


def download_video(url):
    """
    download video
    """
    info = get_m3u8([url])[0]
    filePath, isSkip = get_file(info["videoTitle"], createDir(info["author"]))
    if isSkip:
        print("已存在,跳过:", info["videoTitle"], url, info["m3u8_url"])
        return
    print("download:", info["videoTitle"], info["m3u8_url"])
    download_m3u8(info["m3u8_url"], filePath)  # 也可以用videoTitle


def download_user(url):
    """
    download all user videos
    """
    url=url.split('?')[0]
    pageInfoArr = get_page(url)
    videoInfoArr = get_m3u8([get_domain(url) + i["url"] for i in pageInfoArr])
    for pageInfo, videoInfo in zip(pageInfoArr, videoInfoArr):
        pageInfo.update(videoInfo)
    # return pageInfoArr

    for info in pageInfoArr:
        filePath, isSkip = get_file(info["title"], createDir(info["author"]))
        if isSkip:
            print("已存在,跳过:", info["title"], url, info["m3u8_url"])
            continue
        print("download:", info["title"], info["m3u8_url"])
        download_m3u8(info["m3u8_url"], filePath)  # 也可以用videoTitle


def mix_download(url):
    urlObj = urlparse(url)
    name = urlObj.path.split("/")[1]
    if name == "video":
        download_video(url)
    elif name == "author":
        download_user(url)
    else:
        print("网页路径不匹配", url)


if __name__ == "__main__":
    url = "https://jiuse88.com/video/view/390a6b91aa44932a0196"
    fire.Fire(
        {
            "md": mix_download,
            "du": download_user,  # download all video from user page
            "dv": download_video,  # dwonload one video from video page
            "gm": get_m3u8,
            "dm": download_m3u8,
            "gp": get_page,
            "gpo": get_page_one,
        }
    )
