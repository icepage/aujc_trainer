import asyncio
import base64
import cv2
import ddddocr
import io
import random
import os
from PIL import Image
import re
import time

def get_tmp_dir(tmp_dir:str = './tmp'):
    # 检查并创建 tmp 目录（如果不存在）
    if not os.path.exists(tmp_dir):
        os.makedirs(tmp_dir)
    return tmp_dir


def ddddocr_find_files_pic(target_file, background_file) -> int:
    """
    比对文件获取滚动长度
    """
    with open(target_file, 'rb') as f:
        target_bytes = f.read()
    with open(background_file, 'rb') as f:
        background_bytes = f.read()
    target = ddddocr_find_bytes_pic(target_bytes, background_bytes)
    return target


def ddddocr_find_bytes_pic(target_bytes, background_bytes) -> int:
    """
    比对bytes获取滚动长度
    """
    det = ddddocr.DdddOcr(det=False, ocr=False, show_ad=False)
    res = det.slide_match(target_bytes, background_bytes, simple_target=True)
    return res['target'][0]


def get_img_bytes(img_src: str) -> bytes:
    """
    获取图片的bytes
    """
    img_base64 = re.search(r'base64,(.*)', img_src)
    if img_base64:
        base64_code = img_base64.group(1)
        # print("提取的Base64编码:", base64_code)
        # 解码Base64字符串
        img_bytes = base64.b64decode(base64_code)
        return img_bytes
    else:
        raise "image is empty"


def get_ocr(**kwargs):
    return ddddocr.DdddOcr(show_ad=False, **kwargs)


def save_img(img_name, img_bytes):
    tmp_dir = get_tmp_dir()
    img_path = os.path.join(tmp_dir, f'{img_name}.png')
    # with open(img_path, 'wb') as file:
    #     file.write(img_bytes)
    # 使用 Pillow 打开图像
    with Image.open(io.BytesIO(img_bytes)) as img:
        # 保存图像到文件
        img.save(img_path)
    return img_path


def get_word(ocr, img_path):
    image_bytes = open(img_path, "rb").read()
    result = ocr.classification(image_bytes)
    return result


def human_like_mouse_move(page, from_x, to_x, y):
    """
    移动鼠标
    """
    # 第一阶段：快速移动到目标附近，耗时 0.28 秒
    fast_duration = 0.28
    fast_steps = 50
    fast_target_x = from_x + (to_x - from_x) * 0.8
    fast_dx = (fast_target_x - from_x) / fast_steps

    for _ in range(fast_steps):
        from_x += fast_dx
        page.mouse.move(from_x, y)
        asyncio.sleep(fast_duration / fast_steps)

    # 第二阶段：稍微慢一些，耗时随机 20 到 31 毫秒
    slow_duration = random.randint(20, 31) / 1000
    slow_steps = 10
    slow_target_x = from_x + (to_x - from_x) * 0.9
    slow_dx = (slow_target_x - from_x) / slow_steps

    for _ in range(slow_steps):
        from_x += slow_dx
        page.mouse.move(from_x, y)
        asyncio.sleep(slow_duration / slow_steps)

    # 第三阶段：缓慢移动到目标位置，耗时 0.3 秒
    final_duration = 0.3
    final_steps = 20
    final_dx = (to_x - from_x) / final_steps

    for _ in range(final_steps):
        from_x += final_dx
        page.mouse.move(from_x, y)
        asyncio.sleep(final_duration / final_steps)


def solve_slider_captcha(page, slider, distance, slide_difference):
    """
    解决移动滑块
    """
    # 等待滑块元素出现
    box = slider.bounding_box()

    # 计算滑块的中心坐标
    from_x = box['x'] + box['width'] / 2
    to_y = from_y = box['y'] + box['height'] / 2

    # 模拟按住滑块
    page.mouse.move(from_x, from_y)
    page.mouse.down()

    to_x = from_x + distance + slide_difference
    # 平滑移动到目标位置
    human_like_mouse_move(page, from_x, to_x, to_y)

    # 放开滑块
    page.mouse.up()


def new_solve_slider_captcha(page, slider, distance, slide_difference):
    # 等待滑块元素出现
    distance = distance + slide_difference
    box = slider.bounding_box()
    page.mouse.move(box['x'] + 10 , box['y'] + 10)
    page.mouse.down()  # 模拟鼠标按下
    page.mouse.move(box['x'] + distance + random.uniform(8, 10), box['y'], steps=5)  # 模拟鼠标拖动，考虑到实际操作中可能存在的轻微误差和波动，加入随机偏移量
    time.sleep(random.randint(1, 5) / 10)  # 随机等待一段时间，模仿人类操作的不确定性
    page.mouse.move(box['x'] + distance, box['y'], steps=10)  # 继续拖动滑块到目标位置
    page.mouse.up()  # 模拟鼠标释放，完成滑块拖动
    time.sleep(3)  # 等待3秒，等待滑块验证结果


def rgba2rgb(img_name, rgba_img_path, tmp_dir: str = './tmp'):
    """
    rgba图片转rgb
    """
    tmp_dir = get_tmp_dir(tmp_dir=tmp_dir)

    # 打开一个带透明度的RGBA图像
    rgba_image = Image.open(rgba_img_path)
    # 创建一个白色背景图像
    rgb_image = Image.new("RGB", rgba_image.size, (255, 255, 255))
    # 将RGBA图像粘贴到背景图像上，使用透明度作为蒙版
    rgb_image.paste(rgba_image, (0, 0), rgba_image)

    rgb_image_path = os.path.join(tmp_dir, f"{img_name}.png")
    rgb_image.save(rgb_image_path)

    return rgb_image_path


def get_zero_or_not(v):
    if v < 0:
        return 0
    return v


def expand_coordinates(x1, y1, x2, y2, N):
    # Calculate expanded coordinates
    new_x1 = get_zero_or_not(x1 - N)
    new_y1 = get_zero_or_not(y1 - N)
    new_x2 = x2 + N
    new_y2 = y2 + N
    return new_x1, new_y1, new_x2, new_y2


def cv2_save_img(img_name, img, tmp_dir:str = './tmp'):
    tmp_dir = get_tmp_dir(tmp_dir)
    img_path = os.path.join(tmp_dir, f'{img_name}.png')
    cv2.imwrite(img_path, img)
    return img_path
