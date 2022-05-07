#!/usr/bin/env python3
# coding: utf-8
import grequests
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import fire
from time import sleep
from pathlib import Path
import re
from m3u8_multithreading_download import (
    m3u8_multithreading_download,
    is_file,
)

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


def download_m3u8(url, name):
    """
    download m3u8 url
    """
    import subprocess

    command = f'ffmpeg -y -nostdin -http_proxy {http_proxy} -i "{url}" -c copy "{name}"'

    res = subprocess.call(command, shell=True)
    # the method returns the exit code

    # print("Returned Value: ", res)


def parse_m3u8(text):
    soup = BeautifulSoup(text, "html.parser")
    titleEl = soup.select_one(".container-title")
    title = titleEl.text.strip()
    videoEl = soup.select_one("#video-play")
    m3u8_url = videoEl["data-src"].strip()

    likeEl = soup.select_one(".likeBtn")
    like = likeEl.text.strip()
    dislikeEl = soup.select_one(".dislikeBtn")
    dislike = dislikeEl.text.strip()
    favoriteEl = soup.select_one(".favoriteBtn span")
    favorite = favoriteEl.text.strip()

    tabEl = soup.select_one("#videoShowTabAbout")
    authorEl = tabEl.select("div div:nth-child(1)")[-1].select_one("a")
    author = authorEl.text.strip()
    authorUrl = authorEl["href"].strip()
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


def get_page(url, maxNum=24 * 2, sec=0):
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
            if len(dataArr) >= maxNum:
                return dataArr[0:maxNum]
            sleep(sec)
            print(f"page {num} sleep {sec} ...")
            otherPage = get_page_one(url + f"?page={num}")
            dataArr.extend(otherPage["data"])
    return dataArr[0:maxNum]


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

        pageLinkArr = [
            i.text for i in soup.select(".page-link") if i.text not in filterArr
        ]
        pageCount = int(pageLinkArr[-1]) if pageLinkArr else 1
        data = [
            {
                "title": el.select_one(".title").text.strip(),
                "url": el.select_one(".title")["href"].strip(),
                "author": el.select_one(".text-sub-title a").text.strip(),
            }
            for el in videoElArr
        ]
        return {"pageCount": pageCount, "data": data}


def get_file_path(author, title, dataDir="data_files"):
    fileName = validateName(f'{title}".mp4"', "")  # 把文件名净化成windows安全的字符
    filePath = Path(dataDir) / author / fileName
    return filePath


def get_cache_dir(path, cacheDir="cache_files"):
    """path arg from get_file_path function"""
    return Path(cacheDir) / path.parent.name / path.stem


def download_video(url, lastTitle=""):
    """
    download video
    url: https://jiuse88.com/video/view/2138052877
    lastTitle: 这个参数是当分类页面和视频页面标题不一致的时候,用来打印区别的,不影响运行逻辑
    """
    info = get_m3u8_one(url)

    filePath = get_file_path(
        info["author"], info["videoTitle"]
    )  # 一定要用videoTitle,别用page里的title,因为会添加前缀后缀
    filePath, isSkip = is_file(filePath)
    if isSkip:
        print(
            "check video info - 已存在,跳过:",
            info["author"],
            info["videoTitle"],
            url,
            info["m3u8_url"],
        )
        print("标题一致?", info["videoTitle"] == lastTitle)
        return filePath
    # print("start downloading:", info["author"], info["videoTitle"], info["m3u8_url"])

    # download_m3u8(info["m3u8_url"], filePath)  #用ffmpeg直接下载
    m3u8_multithreading_download(
        info["m3u8_url"], get_cache_dir(filePath), filePath
    )  # 多线程下载,再用ffmpeg合并
    return filePath


def create_playlist(paths, category):
    if not category:
        return
    filePath = Path(f"{category}.m3u8")
    data = []
    if filePath.is_file():
        with open(filePath, "r", encoding="utf8") as f:
            data = f.readlines()
    m3u8Title = "#EXTM3U8\n"
    if len(data) > 0:
        data = data[1:] if data[0] == m3u8Title else data
    for p in paths:
        p = p.as_posix() + "\n"
        if p not in data:
            data.append(p)
    data = [i.strip() + "\n" for i in data if i.strip()]
    with open(filePath, "w", encoding="utf8") as f:
        f.write(m3u8Title)
        f.writelines(data)


def cleanBlank(title):
    return "".join([i for i in title if i.strip()])


def cleanTitleArr(title):
    startArr = ["[原创] "]
    startTitleArr = [
        title[len(startText) :] if title.startswith(startText) else title
        for startText in startArr
    ]
    endArr = [" 已更新", "(有完整版)"]
    endTitleArr = [
        startTitle[: -len(endText)] if startTitle.endswith(endText) else startTitle
        for endText in endArr
        for startTitle in startTitleArr
    ]
    replaceArr = [["（主页已更新）", ""]]
    replaceTitleArr = [
        startTitle.replace(key, value, 1)
        for key, value in replaceArr
        for startTitle in startTitleArr
    ]
    return [
        cleanBlank(title),
        *[cleanBlank(i) for i in startTitleArr],
        *[cleanBlank(i) for i in endTitleArr],
        *[cleanBlank(i) for i in replaceTitleArr],
    ]


def check_skip(info, titleArr):
    """
    因为page页面title会有很多前缀后缀,所以要过滤,不过进入视频页面后title就干净了,uses页面也是干净的
    这种前缀很杂乱,只能过滤大部分,剩下的去video页面过滤
    """
    for title in titleArr:
        filePath = get_file_path(info["author"], title)
        filePath, isSkip = is_file(filePath)
        if isSkip:
            return [filePath, True]
    return [filePath, False]


def download_user(url, maxNum, category=""):
    """
    download all user videos
    """
    url = url.split("?")[0]
    pageInfoArr = get_page(url, maxNum)
    print("start videos:", len(pageInfoArr))
    filePathArr = []
    for idx, info in enumerate(pageInfoArr):  # onebyone 因为并发的话,服务器会有时间戳限制,过期就无法请求了
        print("\n")
        print(f"start: {idx+1}/{len(pageInfoArr)}", info["title"], info["url"])
        titleArr = (
            cleanTitleArr(info["title"]) if category else [info["title"].strip()]
        )  # 过滤一下标题
        [filePath, isSkip] = check_skip(info, titleArr)
        if isSkip:
            print("check page info - 已存在,跳过:", filePath, url)
            filePathArr.append(filePath)
            continue
        filePath = download_video(get_domain(url) + info["url"], info["title"])
        filePathArr.append(filePath)
        print(f"end: {idx+1}/{len(pageInfoArr)}", info["title"], info["url"])
        print("\n")

    create_playlist(filePathArr, category)


def download_category(url, maxNum):
    """
    download category
    url example:
    https://jiuse88.com/video/category/recent-favorite
    https://jiuse88.com/video/category/hot-list
    https://jiuse88.com/video/category/ori
    https://jiuse88.com/video/category/month-discuss
    https://jiuse88.com/video/category/top-favorite
    https://jiuse88.com/video/category/most-favorite
    https://jiuse88.com/video/category/top-list
    https://jiuse88.com/video/category/top-last
    """
    uSplit = url.split("category")
    category = uSplit[1].split("/")[1]
    url = uSplit[0] + "category" + "/" + category
    download_user(url, maxNum, category)


def mix_download(url, maxNum=24 * 2):
    """
    url: https://jiuse88.com/author/Nectarina%E6%B0%B4%E8%9C%9C%E6%A1%83
    max: max videos number, user页面和category页面需要填(忽略则使用默认值),如果是单个video页面就不用填了,填了也忽略
    """
    urlObj = urlparse(url)
    seg = urlObj.path.split("/")
    if seg[2] == "category":
        download_category(url, maxNum)
    elif seg[1] == "video":
        download_video(url)
    elif seg[1] == "author":
        download_user(url, maxNum)
    else:
        print("网页路径不匹配", url)


if __name__ == "__main__":
    url = "https://jiuse88.com/video/view/390a6b91aa44932a0196"
    fire.Fire(
        {
            "md": mix_download,
            "dv": download_video,  # dwonload one video from video page
            "du": download_user,  # download all video from user page
            "dc": download_category,  # download all video from category
            "gm": get_m3u8,
            "dm": download_m3u8,
            "gp": get_page,
            "gpo": get_page_one,
            "mmd": m3u8_multithreading_download,
        }
    )
