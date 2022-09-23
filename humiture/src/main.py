#!/usr/bin/env python
# -*- encoding: utf-8 -*-
'''
@File       :    main.py
@Description:    温湿度上云
@Author     :    ethan.lcz
@version    :    1.0
'''
from aliyunIoT import Device      # aliyunIoT组件是连接阿里云物联网平台的组件
import netmgr as nm               # Wi-Fi功能所在库
import utime                      # 延时API所在组件
from driver import I2C            # I2C总线驱动库
import sh1106              # SH1106 OLED驱动库
from driver import SPI     # 引入SPI总线库
from driver import GPIO           # ESP32和使用GPIO控制LED
from haaseduk1 import HAASEDUK1   # 引入haaseduk1库，目标用于区分K1版本
import ujson                      # json字串解析库
import framebuf            # framebuf基类，用于设置字体库



# 物联网平台连接标志位
iot_connected = False

# 物联网设备实例
device = None

# 三元组信息
productKey = "hoiklCoxoIa"
deviceName = "Temperature-Humidity-Detector"
deviceSecret = "75b8a6b73e0d3045a9fe728696c639c7"


# Wi-Fi SSID和Password设置
wifiSsid = "360WiFi"
wifiPassword = "20090104"

# 空调和加湿器状态变量
airconditioner = 0
humidifier = 0
airconditioner_value = 0
humidifier_value = 0

humitureDev = 0
board = HAASEDUK1()                  # 新建HAASEDUK1对象
hwID = board.getHWID()               # 获取开发板ID
i2cObj = I2C()

if (hwID == 1):
    from cht8305 import CHT8305      # HaaS EDU K1C上的温湿度传感器采用的是CHT8305
    i2cObj.open("cht8305")           # 按照board.json中名为"cht8305"的设备节点的配置参数（主设备I2C端口号，从设备地址，总线频率等）初始化I2C类型设备对象
    humitureDev = CHT8305(i2cObj)   # 初始化CHT8305传感器
    print("cht8305 inited!")
else:
    from si7006 import SI7006        # HaaS EDU K1上的温湿度传感器采用的是SI7006
    i2cObj.open("si7006")            # 按照board.json中名为"si7006"的设备节点的配置参数（主设备I2C端口号，从设备地址，总线频率等）初始化I2C类型设备对象
    humitureDev = SI7006(i2cObj)   # 初始化SI7006传感器
    version = humitureDev.getVer()  # 获取SI7006的版本信息
    chipID = humitureDev.getID()    # 获取SI7006 ID信息
    print("si7006 version:%d, chipID:%d" , version, chipID)

# OLED初始化
def oledInit():
    global oled

    # 字库文件存放于项目目录 font, 注意若用到了中英文字库则都需要放置
    framebuf.set_font_path(framebuf.FONT_ASC12_8, '/data/font/ASC12_8')
    framebuf.set_font_path(framebuf.FONT_ASC16_8, '/data/font/ASC16_8')
    framebuf.set_font_path(framebuf.FONT_ASC24_12, '/data/font/ASC24_12')
    framebuf.set_font_path(framebuf.FONT_ASC32_16, '/data/font/ASC32_16')

    oled_spi = SPI()
    oled_spi.open("oled_spi")

    oled_res = GPIO()
    oled_res.open("oled_res")

    oled_dc = GPIO()
    oled_dc.open("oled_dc")

    #oled像素132*64
    oled = sh1106.SH1106_SPI(132, 64, oled_spi, oled_dc, oled_res)

# OLED显示
# text:显示的文本
# x:水平坐标 y:垂直坐标
# color:颜色
# clear: True-清屏显示 False-不清屏显示
# sz:字体大小
def oledShowText(text, x, y, color, clear, sz):
    global oled
    if clear:
        oled.fill(0) # 清屏
    oled.text(text, x, y, color, size = sz)
    oled.show()

# 等待Wi-Fi成功连接到路由器
def get_wifi_status():
   nm.init()
   nm.disconnect()
   wifi_connected = nm.getStatus()
   print("start to connect " , wifiSsid)
   nm.connect(wifiSsid, wifiPassword)       # 连接到指定的路由器（路由器名称为wifiSsid, 密码为：wifiPassword）

   while True :
      if wifi_connected == 5:               # nm.getStatus()返回5代表连线成功
        break
      else:
        wifi_connected = nm.getStatus() # 获取Wi-Fi连接路由器的状态信息
        utime.sleep(0.5)
   print("Wi-Fi connected")
   print('DeviceIP:' + nm.getInfo()['ip'])  # 打印Wi-Fi的IP地址信息

# 通过温湿度传感器读取温湿度信息
def get_temp_humi():
    global humitureDev
    '''
    # 如果需要同时获取温湿度信息，可以呼叫getTempHumidity，实例代码如下:
    humniture = humitureDev.getTempHumidity()          # 获取温湿度传感器测量到的温湿度值
    temperature = humniture[0]                          # get_temp_humidity返回的字典中的第一个值为温度值
    humidity = humniture[1]                             # get_temp_humidity返回的字典中的第二个值为相对湿度值
    '''
    temperature = humitureDev.getTemperature()         # 获取温度测量结果
    # print("The temperature is: %.1f" % temperature)

    humidity = humitureDev.getHumidity()               # 获取相对湿度测量结果
    # print("The humidity is: %d" % humidity)

    temp_str = "T:%.2f" % temperature
    humi_str = "H:%.2f%%" % humidity
    oledShowText(temp_str, 3, 1, 1, True, 12)
    oledShowText(humi_str, 3, 16, 1, False, 12)

    return temperature, humidity                        # 返回读取到的温度值和相对湿度值

# 物联网平台连接成功的回调函数
def on_connect(data):
    global iot_connected
    iot_connected = True

# 设置props 事件接收函数（当云平台向设备下发属性时）
def on_props(request):
    global airconditioner, humidifier, airconditioner_value, humidifier_value

    # {"airconditioner":1} or {"humidifier":1} or {"airconditioner":1, "humidifier":1}
    payload = ujson.loads(request['params'])
    # print (payload)
    # 获取dict状态字段 注意要验证键存在 否则会抛出异常
    if "airconditioner" in payload.keys():
        airconditioner_value = payload["airconditioner"]
        if (airconditioner_value):
            print("打开空调")
        else:
            print("关闭空调")

    if "humidifier" in payload.keys():
        humidifier_value = payload["humidifier"]
        if (humidifier_value):
            print("打开加湿器")
        else:
            print("关闭加湿器")

    # print(airconditioner_value, humidifier_value)

    airconditioner.write(airconditioner_value) # 控制空调开关
    humidifier.write(humidifier_value)         # 控制加湿器开关

    # 要将更改后的状态同步上报到云平台
    prop = ujson.dumps({
        'airconditioner': airconditioner_value,
        'humidifier': humidifier_value,
    })

    upload_data = {'params': prop}
    # 上报空调和加湿器属性到云端
    device.postProps(upload_data)


# 连接物联网平台
def connect_lk(productKey, deviceName, deviceSecret):
    global device, iot_connected
    key_info = {
        'region': 'cn-shanghai',
        'productKey': productKey,
        'deviceName': deviceName,
        'deviceSecret': deviceSecret,
        'keepaliveSec': 60
    }
    # 将三元组信息设置到iot组件中
    device = Device()

    # 设定连接到物联网平台的回调函数，如果连接物联网平台成功，则调用on_connect函数
    device.on(Device.ON_CONNECT, on_connect)

    # 配置收到云端属性控制指令的回调函数，如果收到物联网平台发送的属性控制消息，则调用on_props函数
    device.on(Device.ON_PROPS, on_props)

    # 启动连接阿里云物联网平台过程
    device.connect(key_info)

    # 等待设备成功连接到物联网平台
    while(True):
        if iot_connected:
            print('物联网平台连接成功')
            break
        else:
            print('sleep for 1 s')
            utime.sleep(1)
    
    oledInit()

# 上传温度信息和湿度信息到物联网平台
def upload_temperature_and_Humidity():
    global device

    while True:
        data = get_temp_humi()                      # 读取温度信息和湿度信息

        # 生成上报到物联网平台的属性值字串
        prop = ujson.dumps({
            'CurrentTemperature': data[0],
            'CurrentHumidity': data[1]
            })
        print('uploading data: ', prop)

        upload_data = {'params': prop}
        # 上传温度和湿度信息到物联网平台
        device.postProps(upload_data)
        utime.sleep(2)

if __name__ == '__main__':
    # 硬件初始化
    # 初始化 GPIO
    airconditioner = GPIO()
    humidifier = GPIO()

    humidifier.open('led_g')     # 加湿器使用board.json中led_g节点定义的GPIO，对应HaaS EDU K1上的绿灯
    airconditioner.open('led_b') # 空调使用board.json中led_b节点定义的GPIO，对应HaaS EDU K1上的蓝灯

    # 请替换物联网平台申请到的产品和设备信息,可以参考文章:https://blog.csdn.net/HaaSTech/article/details/114360517
    # global productKey, deviceName, deviceSecret ,on_request, on_play
    get_wifi_status()

    connect_lk(productKey, deviceName, deviceSecret)
    upload_temperature_and_Humidity()

humitureDev.close()