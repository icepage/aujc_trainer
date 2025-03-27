import argparse
import shutil
import re
import cv2
from loguru import logger
import os
from playwright.sync_api import Playwright, sync_playwright
import random
from PIL import Image  # 用于图像处理
import traceback
from typing import Union
import time
from utils.consts import (
    jd_login_url,
    user_agent
)
from utils.tools import (
    get_tmp_dir,
    get_img_bytes,
    save_img,
    get_ocr,
    new_solve_slider_captcha,
    ddddocr_find_files_pic,
    expand_coordinates,
    cv2_save_img,
    ddddocr_find_bytes_pic,
    solve_slider_captcha,
    rgba2rgb,
    get_word
)

"""
基于playwright做的
"""
logger.add(
    sink="main.log",
    level="DEBUG"
)


def generate_random_user_pass(users, passwords):
    """
    从给定的用户列表和密码列表中随机生成一个用户和密码的组合。

    :param users: 用户列表
    :param passwords: 密码列表
    :return: 一个元组 (user, password)
    """
    if not users or not passwords:
        raise ValueError("用户列表和密码列表不能为空")

    # 随机选择一个用户和一个密码
    user = random.choice(users)
    password = random.choice(passwords)

    return user, password


def generate_random_hash(length=32):
    import hashlib
    import string
    """生成一个随机哈希字符串"""
    random_string = ''.join(random.choices(string.ascii_letters + string.digits, k=16))
    return hashlib.md5(random_string.encode()).hexdigest()[:length]


def auto_move_slide(page, retry_times: int = 2, slider_selector: str = 'img.move-img', move_solve_type: str = ""):
    """
    自动识别移动滑块验证码
    """
    for i in range(retry_times):
        logger.info(f'第{i + 1}次尝试自动移动滑块中...')
        try:
            # 查找小图
            page.wait_for_selector('#small_img', state='visible', timeout=3000)
        except Exception as e:
            # 未找到元素，认为成功，退出循环
            logger.info('未找到小图,退出移动滑块')
            break

        # 获取 src 属性
        small_src = page.locator('#small_img').get_attribute('src')
        background_src = page.locator('#cpc_img').get_attribute('src')

        # 获取 bytes
        small_img_bytes = get_img_bytes(small_src)
        background_img_bytes = get_img_bytes(background_src)

        # 保存小图
        small_img_path = save_img('small_img', small_img_bytes)
        small_img_width = page.evaluate('() => { return document.getElementById("small_img").clientWidth; }')  # 获取网页的图片尺寸
        small_img_height = page.evaluate('() => { return document.getElementById("small_img").clientHeight; }')  # 获取网页的图片尺寸
        small_image = Image.open(small_img_path)  # 打开图像
        resized_small_image = small_image.resize((small_img_width, small_img_height))  # 调整图像尺寸
        resized_small_image.save(small_img_path)  # 保存调整后的图像
        # 保存大图
        background_img_path = save_img('background_img', background_img_bytes)
        background_img_width = page.evaluate('() => { return document.getElementById("cpc_img").clientWidth; }')  # 获取网页的图片尺寸
        background_img_height = page.evaluate('() => { return document.getElementById("cpc_img").clientHeight; }')  # 获取网页的图片尺寸
        background_image = Image.open(background_img_path)  # 打开图像
        resized_background_image = background_image.resize((background_img_width, background_img_height))  # 调整图像尺寸
        resized_background_image.save(background_img_path)  # 保存调整后的图像
        # 获取滑块
        slider = page.locator(slider_selector)
        time.sleep(1)
        # 这里是一个标准算法偏差
        slide_difference = 10

        if move_solve_type == "old":
            # 用于调试
            distance = ddddocr_find_bytes_pic(small_img_bytes, background_img_bytes)
            time.sleep(1)
            solve_slider_captcha(page, slider, distance, slide_difference)
            time.sleep(1)
            continue
        # 获取要移动的长度
        distance = ddddocr_find_files_pic(small_img_path, background_img_path)
        time.sleep(1)

        # 移动滑块
        new_solve_slider_captcha(page, slider, distance, slide_difference)
        time.sleep(1)

        if i + 1 == retry_times:
            raise Exception("滑块识别失败")

def auto_shape_v2(page, import_onnx_path, charsets_path, retry_times: int = 5):
    """
    自动识别滑块验证码
    """
    # 图像识别
    ocr = get_ocr(beta=True)
    # 文字识别
    det = get_ocr(det=True)
    # 自己训练的ocr
    my_ocr = get_ocr(det=False, ocr=False, import_onnx_path=import_onnx_path, charsets_path=charsets_path)
    correct_count = 0
    for i in range(retry_times):
        logger.info(f'第{i + 1}次自动识别形状中...')
        try:
            # 查找小图
            page.wait_for_selector('div.captcha_footer img', state='visible', timeout=3000)
        except Exception as e:
            # 未找到元素，认为成功，退出循环
            logger.info('未找到形状图,退出识别状态')
            break

        tmp_dir = get_tmp_dir()

        background_img_path = os.path.join(tmp_dir, f'background_img.png')
        # 获取大图元素
        background_locator = page.locator('#cpc_img')
        # 获取元素的位置和尺寸
        backend_bounding_box = background_locator.bounding_box()
        backend_top_left_x = backend_bounding_box['x']
        backend_top_left_y = backend_bounding_box['y']

        # 截取元素区域
        page.screenshot(path=background_img_path, clip=backend_bounding_box)

        # 获取 图片的src 属性和button按键
        word_img_src = page.locator('div.captcha_footer img').get_attribute('src')
        button = page.locator('div.captcha_footer button#submit-btn')

        # 找到刷新按钮
        refresh_button = page.locator('.jcap_refresh')


        # 获取文字图并保存
        word_img_bytes = get_img_bytes(word_img_src)
        rgba_word_img_path = save_img('rgba_word_img', word_img_bytes)

        # 文字图是RGBA的，有蒙板识别不了，需要转成RGB
        rgb_word_img_path = rgba2rgb('rgb_word_img', rgba_word_img_path)

        # 获取问题的文字
        word = get_word(ocr, rgb_word_img_path)

        logger.info(f'开始文字识别')
        # 获取文字的顺序列表
        try:
            target_char_list = list(re.findall(r'[\u4e00-\u9fff]+', word)[1])
        except IndexError:
            logger.info(f'识别文字出错,刷新中......')
            refresh_button.click()
            time.sleep(random.uniform(2, 4))
            continue

        target_char_len = len(target_char_list)

        # 识别字数不对
        if target_char_len < 4:
            logger.info(f'识别文字出错,刷新中......')
            refresh_button.click()
            time.sleep(random.uniform(2, 4))
            continue

        # 取前4个的文字
        target_char_list = target_char_list[:4]

        # 定义【文字, 坐标】的列表
        target_list = [[x, []] for x in target_char_list]

        # 获取大图的二进制
        background_locator = page.locator('#cpc_img')
        background_locator_src = background_locator.get_attribute('src')
        background_locator_bytes = get_img_bytes(background_locator_src)
        bboxes = det.detection(background_locator_bytes)

        count = 0
        im = cv2.imread(background_img_path)
        for bbox in bboxes:
            # 左上角
            x1, y1, x2, y2 = bbox
            # 做了一下扩大
            expanded_x1, expanded_y1, expanded_x2, expanded_y2 = expand_coordinates(x1, y1, x2, y2, 10)
            im2 = im[expanded_y1:expanded_y2, expanded_x1:expanded_x2]
            img_path = cv2_save_img('word', im2)
            image_bytes = open(img_path, "rb").read()
            result = my_ocr.classification(image_bytes)
            if result in target_char_list:
                for index, target in enumerate(target_list):
                    if result == target[0] and target[0] is not None:
                        x = x1 + (x2 - x1) / 2
                        y = y1 + (y2 - y1) / 2
                        target_list[index][1] = [x, y]
                        count += 1

        if count != target_char_len:
            time.sleep(random.uniform(2, 4))
        else:
            correct_count += 1
        refresh_button.click()

    logger.info(f"识别完成, 识别率为 {correct_count}/{retry_times}={int(correct_count/retry_times*100)}%")




def auto_shape(page, retry_times: int = 5, pic_dir: str = './tmp'):
    # 图像识别
    ocr = get_ocr(beta=True)
    # 文字识别
    det = get_ocr(det=True)
    # 自己训练的ocr, 提高文字识别度
    my_ocr = get_ocr(det=False, ocr=False, import_onnx_path="myocr_v1.onnx", charsets_path="charsets.json")
    """
    自动识别滑块验证码
    """
    for i in range(retry_times):
        logger.info(f'第{i + 1}次自动识别形状中...')
        try:
            # 查找小图
            page.wait_for_selector('div.captcha_footer img', state='visible', timeout=3000)

            tmp_dir = get_tmp_dir()

            background_img_path = os.path.join(tmp_dir, f'background_img.png')
            # 获取大图元素
            background_locator = page.locator('#cpc_img')
            # 获取元素的位置和尺寸
            backend_bounding_box = background_locator.bounding_box()

            # 截取元素区域
            page.screenshot(path=background_img_path, clip=backend_bounding_box)

            # 找到刷新按钮
            refresh_button = page.locator('.jcap_refresh')

            # 获取文字图并保存
            word_img_src = page.locator('div.captcha_footer img').get_attribute('src')
            word_img_bytes = get_img_bytes(word_img_src)
            rgba_word_img_path = save_img('rgba_word_img', word_img_bytes)

            # 文字图是RGBA的，有蒙板识别不了，需要转成RGB
            rgb_word_img_path = rgba2rgb('rgb_word_img', rgba_word_img_path)

            # 获取问题的文字
            word = get_word(ocr, rgb_word_img_path)

            logger.info(f'开始文字识别,下载中...')

            try:
                target_char = re.findall(r'[\u4e00-\u9fff]+', word)[1]
                with open("./idioms.txt", 'a+') as f:
                    f.writelines(f"\n{target_char}")
            except IndexError:
                logger.info(f'识别文字出错,刷新中......')
                pass

            # 获取大图的二进制
            background_locator = page.locator('#cpc_img')

            background_locator_src = background_locator.get_attribute('src')

            background_locator_bytes = get_img_bytes(background_locator_src)

            bboxes = det.detection(background_locator_bytes)

            im = cv2.imread(background_img_path)
            for bbox in bboxes:
                # 左上角
                x1, y1, x2, y2 = bbox
                # 做了一下扩大
                expanded_x1, expanded_y1, expanded_x2, expanded_y2 = expand_coordinates(x1, y1, x2, y2, 10)
                im2 = im[expanded_y1:expanded_y2, expanded_x1:expanded_x2]
                img_path = cv2_save_img('word', im2)
                image_bytes = open(img_path, "rb").read()
                # 这个是字的结果
                word = my_ocr.classification(image_bytes)
                hash_value = generate_random_hash(length=32)

                try:
                    pic_dir = get_tmp_dir(pic_dir)
                    new_img_name = f"{word}_{hash_value}.png"

                    # 构建新文件路径
                    new_img_path = os.path.join(pic_dir, new_img_name)
                    # 重命名并移动文件
                    shutil.move(img_path, new_img_path)
                except OSError as e:
                    logger.info(e)
                    continue

            refresh_button.click()
            time.sleep(random.uniform(3, 5))
            continue

        except Exception as e:
            traceback.print_exc()
            # 未找到元素，认为成功，退出循环
            logger.info('未找到形状图,退出识别状态')
            break

def get_jd_pt_key(playwright: Playwright, char_args, mode: str) -> Union[str, None]:
    """
    获取jd的pt_key
    """
    headless = False

    args = '--no-sandbox', '--disable-setuid-sandbox'

    browser = playwright.chromium.launch(headless=headless, args=args)
    context = browser.new_context(user_agent=user_agent)

    try:
        page = context.new_page()
        page.set_viewport_size({"width": 360, "height": 640})
        page.goto(jd_login_url)

        page.get_by_text("账号密码登录").click()
        users = ["13500000001", "13500000002", "13500000003", "13500000004"]
        passwords = ["123456798", "qwert", "admin", "letmein"]
        user, password = generate_random_user_pass(users, passwords)
        username_input = page.locator("#username")
        for u in user:
            username_input.type(u, no_wait_after=True)
            time.sleep(random.random() / 10)

        password_input = page.locator("#pwd")
        for p in password:
            password_input.type(p, no_wait_after=True)
            time.sleep(random.random() / 10)

        time.sleep(random.random())
        page.locator('.policy_tip-checkbox').click()
        time.sleep(random.random())
        page.locator('.btn.J_ping.active').click()

        # 自动识别移动滑块验证码
        time.sleep(1)

        auto_move_slide(page, retry_times=5, move_solve_type="old")

        # 自动验证形状验证码
        time.sleep(1)
        if mode == "get_char":
            auto_shape(page, retry_times=char_args.frequency, pic_dir=char_args.dir)
        elif mode == "test_model":
            auto_shape_v2(page, import_onnx_path=char_args.import_onnx_path, charsets_path=char_args.charsets_path, retry_times=char_args.retry_times)

        return None

    except Exception as e:
        traceback.print_exc()
        return None

    finally:
        context.close()
        browser.close()

def get_char(args):
    try:
        # 登录JD获取pt_key
        with sync_playwright() as playwright:
            get_jd_pt_key(playwright, char_args=args, mode="get_char")
            logger.info("图片采集完成")

    except Exception as e:
        logger.info("图片采集异常退出")
        traceback.print_exc()


def test_char(args):
    img_path = args.img_path
    import_onnx_path= args.import_onnx_path
    charsets_path= args.charsets_path
    my_ocr = get_ocr(det=False, ocr=False, import_onnx_path=import_onnx_path, charsets_path=charsets_path)
    for path in img_path:
        image_bytes = open(path, "rb").read()
        # 这个是字的结果
        word = my_ocr.classification(image_bytes)

        logger.info(f"文件【{path}】, 识别结果为【{word}】")

def test_model(args):
    try:
        # 登录JD获取pt_key
        with sync_playwright() as playwright:
            get_jd_pt_key(playwright, char_args=args, mode="test_model")
            logger.info("图片采集完成")

    except Exception as e:
        logger.info("图片采集异常退出")
        traceback.print_exc()

def main():
    logger.info("欢迎使用aujc_tools")
    parser = argparse.ArgumentParser(description="CLI 工具")

    # 添加子命令
    subparsers = parser.add_subparsers(dest="command", required=True, help="可用的命令")

    # `get_char` 命令, 用于下载训练素材图片
    parser_get_char = subparsers.add_parser("get_char", help="获取训练图片")
    parser_get_char.add_argument("-d", "--dir", type=str, default="./tmp", help="存储路径")
    parser_get_char.add_argument("-f", "--frequency", type=int, default=5, help="采集频率")
    parser_get_char.set_defaults(func=get_char)

    # `test_char` 用于验证试练模型识别图片
    parser_test_char = subparsers.add_parser("test_char", help="测试模型识别图片")
    parser_test_char.add_argument('-i', '--img_path', nargs='+', help="采集图片存放的文件名", required=True)
    parser_test_char.add_argument("-c", "--charsets_path", type=str, help="charsets_path")
    parser_test_char.add_argument("-on", "--import_onnx_path", type=str, help="import_onnx_path")
    parser_test_char.set_defaults(func=test_char)

    # `test_model` 用于验证模型通过JD点选验证码
    parser_test_model = subparsers.add_parser("test_model", help="测试模型通过JD")
    parser_test_model.add_argument("-c", "--charsets_path", type=str, help="charsets_path")
    parser_test_model.add_argument("-on", "--import_onnx_path", type=str, help="import_onnx_path")
    parser_test_model.add_argument("-rt", "--retry_times", type=int, default=5, help="retry_times")
    parser_test_model.set_defaults(func=test_model)

    # 解析命令行参数
    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
