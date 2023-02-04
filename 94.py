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
import json
from m3u8_multithreading_download import (
    m3u8_download,
    get_url,
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
retryMax = 5


def validateName(name, target=""):
    re_str = r"[\/\\\:\*\?\"\<\>\|]"  # '/ \ : * ? " < > |'
    new_name = re.sub(re_str, target, name)
    return new_name


def ffmpeg_download_m3u8(url, name):
    """
    download m3u8 url
    """
    import subprocess

    command = f'ffmpeg -y -nostdin -http_proxy {http_proxy} -i "{url}" -c copy "{name}"'

    res = subprocess.call(command, shell=True)
    # the method returns the exit code

    # print("Returned Value: ", res)


def parse_m3u8(text, url):
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
        "videoId": url.split("?")[0].split("/")[-1],
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
    return [parse_m3u8(response.text, response.url) for response in resArr]


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
                "videoId": el.select_one(".title")["href"].strip().split("/")[-1],
                "title": el.select_one(".title").text.strip(),
                "url": el.select_one(".title")["href"].strip(),
                "author": el.select_one(".text-sub-title a").text.strip(),
            }
            for el in videoElArr
        ]
        return {"pageCount": pageCount, "data": data}


def get_file_path(author, title, vid, dataDir="data_files"):
    title = title.rstrip(".")  # windows会把末尾的.清空
    fileName = validateName(f"{title}_{vid}.mp4", "")  # 把文件名净化成windows安全的字符
    filePath = Path(dataDir) / author / fileName
    return config["outPath"] / filePath


def get_cache_dir(path, cacheDir="cache_files"):
    """path arg from get_file_path function"""
    return config["outPath"] / Path(cacheDir) / path.parent.name / path.stem


def download_video(url, lastTitle=""):
    """
    download video
    url: https://jiuse88.com/video/view/2138052877
    lastTitle: 这个参数是当分类页面和视频页面标题不一致的时候,用来打印区别的,不影响运行逻辑
    """
    response = get_url(url, tag="get_m3u8_url_one")
    info = parse_m3u8(response.text, url)
    filePath = get_file_path(
        info["author"], info["videoTitle"], info["videoId"]
    )  # 一定要用videoTitle,别用page里的title,因为会添加前缀后缀
    filePath, isSkip = is_file(filePath)
    if isSkip:
        print(
            "check video title - 已存在,跳过:",
            info["author"],
            info["videoTitle"],
            url,
            info["m3u8_url"],
        )
        print("标题一致?", info["videoTitle"] == lastTitle)
        return filePath

    [filePathGlob, isSkipGlob] = check_skip_glob(info, filePath)
    if isSkipGlob:
        print(
            "check video id - 已存在,跳过:",
            info["author"],
            info["videoTitle"],
            url,
            info["m3u8_url"],
        )
        print("标题一致?", info["videoTitle"] == lastTitle)
        return filePathGlob

    # ffmpeg_download_m3u8(info["m3u8_url"], filePath)  #用ffmpeg直接下载
    m3u8_download(
        info["m3u8_url"],
        get_cache_dir(filePath),
        filePath,
    )  # 多线程下载,再用ffmpeg合并

    return filePath


def download_video_create_playlist(url, lastTitle=""):
    filePath = download_video(url, lastTitle=lastTitle)
    create_playlist([filePath], "videos")
    return filePath


# def sort_playlist(data, paths):
#     for p in paths:
#         p = p.as_posix() + "\n"
#         if p not in data:
#             data.append(p)
#     return data


def deduplication(data):
    newData = []
    for i in data:
        if i not in newData:
            newData.append(i)
    return newData


def add_playlist(data, paths):
    return [*data, *paths]


def sort_playlist(data, paths):
    # 计算一下总数
    all_data = add_playlist(data, paths)
    all_data = deduplication(all_data)
    print("start playlist", len(data), len(all_data))
    # end
    cursor = -1
    for p in paths:
        if p in data:
            cursor = data.index(p)
        else:
            data.insert(cursor + 1, p)
            cursor = data.index(p)
    print("end playlist  ", len(data), len(all_data))
    # 根据总数判断一下,playlist合并的数量对不对
    if len(all_data) != len(data):
        print(len(data), len(all_data))
        import pdb

        pdb.set_trace()
    # end
    return data


def create_playlist(paths, category):
    if not category:
        return
    if "/" in category:
        (config["outPath"] / category.split("/")[0]).mkdir(exist_ok=True)
    filePath = config["outPath"] / f"{category}.m3u8"
    data = []
    if filePath.is_file():
        with open(filePath, "r", encoding="utf8") as f:
            data = f.readlines()
    m3u8Title = "#EXTM3U8\n"
    if len(data) > 0:
        data = data[1:] if data[0] == m3u8Title else data
    data = [i.strip() for i in data]
    data = deduplication(data)
    paths = [(Path("/".join(i.parts[-3:])).as_posix()).strip() for i in paths]
    paths = deduplication(paths)  # 要是重复的话,sort会追加到第一个的后面去
    data = sort_playlist(data, paths)
    data = deduplication(data)
    data = [i + "\n" for i in data]

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
        *[cleanBlank(i) for i in startTitleArr],
        *[cleanBlank(i) for i in endTitleArr],
        *[cleanBlank(i) for i in replaceTitleArr],
        cleanBlank(title),  # 最后一项放原标题,便于check_skip函数返回
    ]


def check_skip(
    info,
    titleArr,
):
    """
    因为page页面title会有很多前缀后缀,所以要过滤,不过进入视频页面后title就干净了,uses页面也是干净的
    这种前缀很杂乱,只能过滤大部分,剩下的去video页面过滤
    titleArr最后一项放原标题,不跳过则直接返回
    """
    for title in titleArr:
        filePath = get_file_path(info["author"], title, info["videoId"])
        filePath, isSkip = is_file(filePath)
        if isSkip:
            return [filePath, True]
    return [filePath, False]


def check_skip_glob(info, filePath):
    for filePathGlob in Path(filePath.parent).glob(f'*_{info["videoId"]}.mp4'):
        filePathGlob, isSkip = is_file(filePathGlob)
        if isSkip:
            return [filePathGlob, True]
    return [filePath, False]


def blacklist_filter(pageInfoArrOrigin):
    pageInfoArr = []
    blacklistArr = []
    ifAuthor = lambda info: info["author"] in config["blacklist"]["author"]
    ifVideoId = lambda info: info["videoId"] in config["blacklist"]["videoId"]
    for info in pageInfoArrOrigin:
        if ifAuthor(info) or ifVideoId(info):
            blacklistArr.append(info)
        else:
            pageInfoArr.append(info)
    return [pageInfoArr, blacklistArr]


def download_user(url, maxNum, category=""):
    """
    download all user videos
    """
    url = url.split("?")[0]
    pageInfoArrOrigin = get_page(url, maxNum)
    [pageInfoArr, blacklistArr] = blacklist_filter(pageInfoArrOrigin)
    print(
        "start videos:",
        len(pageInfoArr),
        "blacklist videos:",
        len(blacklistArr),
        "count videos:",
        len(pageInfoArrOrigin),
    )
    filePathArr = []
    for idx, info in enumerate(pageInfoArr):  # onebyone 因为并发的话,服务器会有时间戳限制,过期就无法请求了
        videoUrl = get_domain(url) + info["url"]
        print("\n")
        print(
            f"start: {idx+1}/{len(pageInfoArr)}",
            info["author"],
            info["title"],
            videoUrl,
        )

        titleArr = (
            cleanTitleArr(info["title"]) if category else [info["title"].strip()]
        )  # 过滤一下标题
        [filePath, isSkip] = check_skip(info, titleArr)
        if isSkip:
            print("check page title - 已存在,跳过:", filePath, videoUrl)
            filePathArr.append(filePath)
            continue

        [filePathGlob, isSkipGlob] = check_skip_glob(info, filePath)
        if isSkipGlob:
            print("check page id - 已存在,跳过:", filePath, videoUrl)
            filePathArr.append(filePathGlob)
            continue

        filePath = download_video(videoUrl, info["title"])
        filePathArr.append(filePath)
        print(
            f"end: {idx+1}/{len(pageInfoArr)}", info["author"], info["title"], videoUrl
        )
        print("\n")

    if category == "":
        category = "user_playlist/" + info["author"]
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
    download_user(url, maxNum, category)  # 因为user和category的页面结构一样, 所以复用代码


def getConfig(configPath, outPath="./"):
    if not configPath.is_file() or configPath.stat().st_size == 0:
        with open(configPath, "w", encoding="utf-8") as file:
            json.dump(
                {"blacklist": {"videoId": [], "author": []}},
                file,
                ensure_ascii=False,
                indent=4,
            )
    with open(configPath, "r", encoding="utf-8") as file:
        config = json.load(file)
        if "outPath" not in config or not config["outPath"]:
            config["outPath"] = Path(outPath)
        return config


def mix_download(url, maxNum=24 * 2, outPath="./"):
    """
    url: https://jiuse88.com/author/Nectarina%E6%B0%B4%E8%9C%9C%E6%A1%83
    max: max videos number, user页面和category页面需要填(忽略则使用默认值),如果是单个video页面就不用填了,填了也忽略
    """
    global config
    configPath = Path(outPath) / "config.json"
    config = getConfig(configPath, outPath=outPath)

    urlObj = urlparse(url)
    seg = urlObj.path.split("/")
    if seg[2] == "category":
        download_category(url, maxNum)
    elif seg[1] == "video":
        download_video_create_playlist(url)
    elif seg[1] == "author":
        download_user(url, maxNum)
    else:
        print("网页路径不匹配", url)


if __name__ == "__main__":
    url = "https://jiuse88.com/video/view/390a6b91aa44932a0196"
    fire.Fire(
        {
            "md": mix_download,
            "dv": download_video_create_playlist,  # dwonload one video from video page
            "du": download_user,  # download all video from user page
            "dc": download_category,  # download all video from category
            "gm": get_m3u8,
            "gp": get_page,
            "gpo": get_page_one,
            "fdm": ffmpeg_download_m3u8,
            "mdl": m3u8_download,
        }
    )
