LEVELS = {
    "无损压缩": None,
    "轻度压缩 · 高清": (240, 90),
    "标准压缩 · 推荐": (150, 75),
    "强力压缩 · 小体积": (96, 50),
    "极限压缩 · 低清": (72, 30),
}

# Try the highest quality first. Re-read the same source on each attempt.
TARGET_PROFILES = ((150, 75), (120, 60), (96, 45), (72, 35), (60, 28), (48, 20))
