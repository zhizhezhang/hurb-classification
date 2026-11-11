# 网页视觉素材清单

> 2026-10-29 复核：清单中标为“保留原位”的两张图片当前均未在 `herb_classifier/imgs/` 找到，该目录当前不存在。下方迁移记录保留原样，表示素材整理时的核验结果；两张原图的现存位置待确认。

## 范围与方法

迁移前 herb_classifier/imgs/ 共 29 张图片（公共素材 11 张、药材素材 18 张），目标 frontend/public/assets/ 原为空。逐张打开检查内容，使用 Pillow 核验文件实际格式、像素尺寸和透明通道；在迁移前记录 SHA-256。首批移动 21 张；本次依据用户确认再移动 6 张，共 27 张图片，不裁剪、不重编码、不改色、不改变透明度或比例。迁移后重新计算 SHA-256，并与迁移前记录逐项比较，27 张均一致。另有 2 张当时计划保留原位，但本次复核时原目录已不存在，现存位置待确认。迁移记录覆盖原有的 29 张图片，已迁移文件无同名覆盖；18 张药材图均已迁移并有透明像素。

素材整理时，外层 herb_classifier/ 曾是训练工程复用的数据预处理包；后续已将其预处理实现原样保存到内层 convnext-herb-classifier/herb_classifier/preprocessing.py，并移除外层重复包。没有训练或推理代码引用原 herb_classifier/imgs/；素材整理本身未修改 Python 文件或模型类别映射。

## 迁移清单

| 原始路径 | 新路径 | 类别或用途 | 尺寸 | 实际格式 | 透明像素 | 迁移前 SHA-256 | 比对结果 |
|---|---|---|---:|---|---|---|---|
| herb_classifier/imgs/8FE98EAEE7B8_1200x1500.png | frontend/public/assets/panels/recognition_paper_option_01.png | 竖版空白纸备选 01 | 1200×1500 | PNG | 无 | e0a847954c9cdefb5a77bbcba21859aa58b27c8ff446f83aeb10251dbd62f1db | 一致 |
| herb_classifier/imgs/herbs/冬虫夏草科学插画.png | frontend/public/assets/herbs/herb_dongchongxiacao.png | 冬虫夏草 | 1254×1254 | PNG | 有 | 945f6b877d9a686cd0dc7b2aef0e8dbbd01b1fcfb7121a5b870e1dc5addff4e0 | 一致 |
| herb_classifier/imgs/herbs/干柿萼片干燥植物标本.png | frontend/public/assets/herbs/herb_shidi.png | 柿蒂 | 1254×1254 | PNG | 有 | 110a27e35f593861180d6eda3bb59d6fd52ca538a6e45029e8fc37b9d95469fc | 一致 |
| herb_classifier/imgs/herbs/当归根叶花序植物图谱.png | frontend/public/assets/herbs/herb_danggui.png | 当归 | 1254×1254 | PNG | 有 | b24299b80a68de5e76a0a47f0c163afdc65080892bb1f31706199b314519bc6c | 一致 |
| herb_classifier/imgs/herbs/红褐光泽灵芝水彩插画.png | frontend/public/assets/herbs/herb_lingzhi.png | 灵芝 | 1254×1254 | PNG | 有 | b549ec90c3931dffda702f0c54fb4a3cc60918e6c6dd0abdce7fd2dd5e42c4b7 | 一致 |
| herb_classifier/imgs/herbs/罗汉果整果与剖面插画.png | frontend/public/assets/herbs/herb_luohanguo.png | 罗汉果 | 1254×1254 | PNG | 有 | 4f097dd98d09c7cabdc3c07f4fd0b0c84f14792593e5e4c4ca4892ed4687c8c6 | 一致 |
| herb_classifier/imgs/herbs/透明背景上的匍匐绿叶黄花植物插画.png | frontend/public/assets/herbs/herb_jinqiancao.png | 金钱草（用户确认） | 1254×1254 | PNG | 有 | 28b384fd5b90837f1a885e63a583718a59522dcee396b4d794fcdc6d4b169766 | 一致 |
| herb_classifier/imgs/herbs/透明背景上的无花果与绿叶静物插画.png | frontend/public/assets/herbs/herb_wuhuaguo.png | 无花果 | 1402×1122 | PNG | 有 | 8e983c1a9a55161a35fbb7e8cf5f54ca1ea0b9d60b34a8c3d49fca67fdb59680 | 一致 |
| herb_classifier/imgs/herbs/透明背景上的枸杞干果堆.png | frontend/public/assets/herbs/herb_gangouqi.png | 干枸杞 | 1254×1254 | PNG | 有 | 94d3b774524f6e8b3427dc67ea4c532318c733bd544e50f72063e84ea50cfcad | 一致 |
| herb_classifier/imgs/herbs/透明背景上的白黄忍冬花藤插画.png | frontend/public/assets/herbs/herb_jinyinhua.png | 金银花（忍冬） | 1254×1254 | PNG | 有 | fd8458617ab4b8af7ee7882b0e255cdef98be03c581724960b2ec90e545b39d4 | 一致 |
| herb_classifier/imgs/herbs/透明背景上的车前草植物学插画.png | frontend/public/assets/herbs/herb_cheqiancao.png | 车前草 | 1173×1341 | PNG | 有 | cb880e4a44ccaa53e9d1ff7535a7014083062e414855f882859cfde7945d174b | 一致 |
| herb_classifier/imgs/herbs/透明背景人参植物水彩插画.png | frontend/public/assets/herbs/herb_renshen.png | 人参 | 1254×1254 | PNG | 有 | 00a0f07f06a7594221bc6cbf20dedacc01a0e8573e26bf7be7fe0b208bb873e4 | 一致 |
| herb_classifier/imgs/herbs/透明背景的写实芦荟植株.png | frontend/public/assets/herbs/herb_luhui.png | 芦荟 | 1312×1199 | PNG | 有 | 7fcabc29fd95e55bf0750d170fbedf855619962276a53a6fc8a71fc88a33a206 | 一致 |
| herb_classifier/imgs/herbs/透明背景的洋槐花枝 ботanical illustration.png | frontend/public/assets/herbs/herb_huaihua.png | 槐花（用户确认，保留源名记录） | 1254×1254 | PNG | 有 | 8ab35e770d312955833449835540a3cc6e6a820845c7b1a53b42b74b5c08e3ad | 一致 |
| herb_classifier/imgs/herbs/透明背景罗勒花草本插画.png | frontend/public/assets/herbs/herb_jiucengta.png | 九层塔（罗勒） | 1254×1254 | PNG | 有 | 14d469de530c5ffaadd8c54f5cb2472bb917bee6355672ebff8bfbfb8be128da | 一致 |
| herb_classifier/imgs/herbs/透明背景黄芪水彩植物图 亚洲欧美.png | frontend/public/assets/herbs/herb_huangqi.png | 黄芪 | 1254×1254 | PNG | 有 | 4bf26bba4234186e01867b5813fc1b61fe97d996584e7e45eb6e33218a053537 | 一致 |
| herb_classifier/imgs/herbs/金棕色钩刺苍耳种荚簇.png | frontend/public/assets/herbs/herb_cangerzi.png | 苍耳子 | 1402×1122 | PNG | 有 | 9c90a6e98a9110886d0faeaa297141190f02541dd4a90549fe8f90bb0cc76070 | 一致 |
| herb_classifier/imgs/herbs/银绿艾草植物水彩插画.png | frontend/public/assets/herbs/herb_aiye.png | 艾叶 | 1254×1254 | PNG | 有 | 13d8f5bc7b1e7fced3c18855cf2d99f4618924809e0c3d2258d9b9faa34d51e1 | 一致 |
| herb_classifier/imgs/herbs/陈皮干片纹理插画.png | frontend/public/assets/herbs/herb_chenpi.png | 陈皮 | 1254×1254 | PNG | 有 | 6a13652736314380fdc86acafcdbefa23dd66536b3e1454b2c1510eb94de82e0 | 一致 |
| herb_classifier/imgs/中式水墨背景_2560x1440_浅色.png | —（保留原位） | 浅色备用背景，保留版本 | 2560×1440 | PNG | 无 | c199a5e569d9a4dcf93e5f1a71ff911d0607c8bdc32a77a28cb18fb96f012892 | 待确认，未迁移 |
| herb_classifier/imgs/古朴的空白复古书籍.png | frontend/public/assets/books/atlas_open_book.png | 展开的空白复古书籍 | 1536×1024 | PNG | 有 | 1fd50652fae2bcc1e7e556fff3f651228b4e89744a1b15fba3b3d4b4f50bb5aa | 一致 |
| herb_classifier/imgs/古韵山水立轴卷轴.png | frontend/public/assets/scrolls/history_scroll_closed.png | 闭合卷轴 | 1998×787 | PNG | 有 | b8501e454665b8c00e5914bac02d9722080a504dd2b8d7a4ff9cb80054aea2c2 | 一致 |
| herb_classifier/imgs/复古红边空白羊皮纸.png | frontend/public/assets/panels/recognition_paper_option_02.png | 竖版空白纸备选 02 | 941×1672 | PNG | 无 | 996fce9daf4a74d478109f2c77f4f406fa76f6e10b20ec8092e06f7076a4b932 | 一致 |
| herb_classifier/imgs/朱砂灵枝本草印 (1).png | frontend/public/assets/branding/logo_lingzhi_bencao.png | 灵枝本草印章 | 1254×1254 | PNG | 有 | 526c6babfd6f14b7043a8bcdad77b234561c980d6d71fc9da953e60cb6db5a11 | 一致 |
| herb_classifier/imgs/水墨人参识别界面.png | —（保留原位） | 完整界面示意图，不是书或石台素材 | 1672×941 | PNG | 无 | e1df9e18919dadd9542aa6fed19e47bf5b26fee7413dfec3f61334239ff54f74 | 待确认，未迁移 |
| herb_classifier/imgs/水墨山水背景_2560x1440.png | frontend/public/assets/backgrounds/background_landscape.png | 山水主背景 | 2560×1440 | PNG | 无 | 061104a9038bcec4608fbc5c38716ac9d1eb31c8353b8741b4ccf0ed5530b171 | 一致 |
| herb_classifier/imgs/右侧水彩山野枝叶与红果花簇.png | frontend/public/assets/decorations/decoration_right.png | 右侧装饰花枝（源名由用户确认） | 887×1774 | PNG | 有 | bd891b70a23aa11219dc769270c8e9d5676145205cfd433e08df418dc96554a2 | 一致 |
| herb_classifier/imgs/透明背景古韵中式卷轴旗帜.png | frontend/public/assets/scrolls/history_scroll_open.png | 展开卷轴 | 1997×788 | PNG | 有 | 09d0f95e12a749187d3a14a986d072c0e5a4ff0b4c51011b9b492334c2227eca | 一致 |
| herb_classifier/imgs/左侧透明背景的水彩花枝插画.png | frontend/public/assets/decorations/decoration_left.png | 左侧装饰花枝（源名由用户确认） | 887×1774 | PNG | 有 | 39e6e82df2000c206243309f59d6cd460cf61ce48920c70447a7d1b9cb12285b | 一致 |

## 当前素材说明

- 两张竖版空白纸分别命名为 recognition_paper_option_01.png 与 recognition_paper_option_02.png；均为备选，开发时再决定使用哪一张。
- 左右装饰采用用户已重命名的源文件，分别归档为 decoration_left.png 与 decoration_right.png。
- 用户确认原“洋槐花枝”和“匍匐绿叶黄花植物”图片分别用于槐花、金钱草；本清单保留源文件名以便追溯。模型类别映射没有修改。
- 浅色备用背景和完整的“水墨人参识别界面”示意图未迁移；原目录当前不存在，两张文件的现存位置待确认。
- 源目录仍没有可确认的独立石台素材，atlas_stone_platform.png 尚未建立。
- herb_jiucengta.png：源文件标为罗勒，农业部门资料列罗勒别名为九层塔，且图像为罗勒植株；按该通用名称映射。[农业部门资料](https://kmweb.moa.gov.tw/theme_data.php?id=418&theme=plant_illustration)。
