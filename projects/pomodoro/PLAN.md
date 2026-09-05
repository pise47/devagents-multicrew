# 模块拆分
- index.html: 应用主页面。包含计时器显示区、控制按钮（开始、暂停、重置）的HTML结构；所有页面样式（CSS）；计时器核心逻辑（JavaScript）：负责倒计时、状态管理、DOM更新、浏览器标题栏同步以及计时结束提示。

## 接口定义
- HTML 元素标识：
  - `id="timer-display"`: 用于显示“MM:SS”格式的倒计时。
  - `id="start-btn"`: 开始按钮。
  - `id="pause-btn"`: 暂停按钮。
  - `id="reset-btn"`: 重置按钮。
- JavaScript 关键函数：
  - `startTimer()`: 启动或恢复倒计时。
  - `pauseTimer()`: 暂停当前倒计时。
  - `resetTimer()`: 重置倒计时至25:00并停止。
  - `updateDisplay()`: 更新页面计时器显示与浏览器标题栏。
  - `timerEnded()`: 当计时归零时触发，调用浏览器alert。

## 依赖
- 无后端依赖。

## 预期文件清单
- source: index.html  # 单页应用主文件，包含结构、样式与脚本。
- test: smoke.json  # 冒烟测试契约，验证页面加载后关键元素与文本。