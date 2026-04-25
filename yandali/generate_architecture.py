#!/usr/bin/env python3
"""
Nanobot 项目详细架构图生成器
使用 matplotlib 绘制分层架构图
"""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import numpy as np

# 设置中文字体
plt.rcParams['font.family'] = ['DejaVu Sans', 'sans-serif']
plt.rcParams['axes.unicode_minus'] = False

def draw_box(ax, x, y, width, height, text, color, text_color='white', fontsize=9, alpha=0.95, radius=0.03):
    """绘制圆角矩形框"""
    box = FancyBboxPatch(
        (x - width/2, y - height/2), width, height,
        boxstyle=f"round,pad=0.02,rounding_size={radius}",
        facecolor=color, edgecolor='#333333', linewidth=1.2, alpha=alpha, zorder=3
    )
    ax.add_patch(box)
    ax.text(x, y, text, ha='center', va='center', fontsize=fontsize,
            color=text_color, fontweight='bold', wrap=True, zorder=4)
    return box

def draw_arrow(ax, x1, y1, x2, y2, color='#555555', style='->', lw=1.5, connectionstyle="arc3,rad=0"):
    """绘制箭头连接线"""
    ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle=style, color=color, lw=lw,
                               connectionstyle=connectionstyle),
                zorder=2)

def draw_dashed_box(ax, x, y, width, height, label, color, alpha=0.08):
    """绘制虚线分组框"""
    box = FancyBboxPatch(
        (x - width/2, y - height/2), width, height,
        boxstyle="round,pad=0.02,rounding_size=0.05",
        facecolor=color, edgecolor=color, linewidth=2, alpha=alpha, linestyle='--', zorder=1
    )
    ax.add_patch(box)
    ax.text(x, y + height/2 - 0.15, label, ha='center', va='top', fontsize=11,
            color=color, fontweight='bold', alpha=0.7, zorder=2)

# =============================================================================
# 图 1: 整体系统架构图
# =============================================================================
fig1, ax1 = plt.subplots(figsize=(20, 26))
ax1.set_xlim(0, 20)
ax1.set_ylim(0, 26)
ax1.set_aspect('equal')
ax1.axis('off')
ax1.set_facecolor('#fafafa')
fig1.patch.set_facecolor('#fafafa')

# 标题
ax1.text(10, 25.5, 'Nanobot System Architecture', ha='center', va='center',
         fontsize=24, fontweight='bold', color='#1a1a2e')
ax1.text(10, 25.0, 'Lightweight AI Agent Framework — High-Level Overview', ha='center', va='center',
         fontsize=13, color='#555555')

# 颜色定义
C_ENTRY = '#2d3436'      # 入口层
C_CORE = '#0984e3'       # 核心层
C_BUS = '#00b894'        # 总线
C_SUPPORT = '#e17055'    # 支撑层
C_CHANNEL = '#6c5ce7'    # 通道层
C_PROVIDER = '#fdcb6e'   # LLM提供商
C_TOOL = '#d63031'       # 工具层
C_EXTERNAL = '#636e72'   # 外部系统
C_DATA = '#b2bec3'       # 数据层
C_BG = '#dfe6e9'         # 背景

# ==================== 入口层 (最顶层) ====================
draw_dashed_box(ax1, 10, 23.5, 18, 2.2, 'ENTRY POINTS', C_ENTRY)

draw_box(ax1, 3, 23.5, 2.8, 1.2, 'CLI\n(commands.py)', C_ENTRY, fontsize=9)
draw_box(ax1, 7, 23.5, 2.8, 1.2, 'API Server\n(aiohttp)', C_ENTRY, fontsize=9)
draw_box(ax1, 11, 23.5, 2.8, 1.2, 'Gateway\n(WebSocket)', C_ENTRY, fontsize=9)
draw_box(ax1, 15, 23.5, 2.8, 1.2, 'Python SDK\n(Nanobot)', C_ENTRY, fontsize=9)
draw_box(ax1, 18.5, 23.5, 2.2, 1.2, 'Docker', C_ENTRY, fontsize=9)

# 箭头到核心
for x in [3, 7, 11, 15, 18.5]:
    draw_arrow(ax1, x, 22.9, 10, 21.8, color='#555')

# ==================== 核心层 ====================
draw_dashed_box(ax1, 10, 20.8, 18, 2.6, 'CORE ENGINE', C_CORE)

draw_box(ax1, 10, 21.3, 5, 1.6, 'Nanobot\n(Facade)', '#74b9ff', text_color='#2d3436', fontsize=10)
draw_box(ax1, 6, 20.2, 4, 1.2, 'Config\n(Pydantic)', C_CORE, fontsize=9)
draw_box(ax1, 14, 20.2, 4, 1.2, 'SessionManager\n(JSONL)', C_CORE, fontsize=9)

# 箭头
# 入口 -> Nanobot 已在上面
# Config / SessionManager -> Nanobot
draw_arrow(ax1, 6, 20.8, 8.5, 21.3, color='#555')
draw_arrow(ax1, 14, 20.8, 11.5, 21.3, color='#555')

# ==================== Agent 循环层 ====================
draw_dashed_box(ax1, 10, 17.8, 18, 4.0, 'AGENT LOOP', '#0984e3')

draw_box(ax1, 10, 19.0, 5.5, 1.8, 'AgentLoop\n(Event Loop)', '#0984e3', fontsize=11)

draw_box(ax1, 4.5, 17.8, 3.5, 1.4, 'AgentRunner\n(LLM + Tools)', '#74b9ff', text_color='#2d3436', fontsize=9)
draw_box(ax1, 9, 17.8, 3.5, 1.4, 'ContextBuilder\n(Prompt)', '#74b9ff', text_color='#2d3436', fontsize=9)
draw_box(ax1, 13.5, 17.8, 3.5, 1.4, 'ToolRegistry\n(Tools)', '#74b9ff', text_color='#2d3436', fontsize=9)
draw_box(ax1, 18, 17.8, 3.5, 1.4, 'AgentHook\n(Lifecycle)', '#74b9ff', text_color='#2d3436', fontsize=9)

# AgentLoop 内部连接
draw_arrow(ax1, 10, 19.9, 10, 20.45, color='#333')
draw_arrow(ax1, 10, 18.1, 10, 17.2, color='#333')

# AgentLoop <-> 子组件
draw_arrow(ax1, 7.75, 19.0, 6.25, 18.5, color='#333')
draw_arrow(ax1, 8.5, 19.0, 9.0, 18.5, color='#333')
draw_arrow(ax1, 11.5, 19.0, 13.0, 18.5, color='#333')
draw_arrow(ax1, 12.75, 19.0, 16.25, 18.5, color='#333')

# ==================== 消息总线层 ====================
draw_dashed_box(ax1, 10, 14.8, 18, 2.2, 'MESSAGE BUS', C_BUS)

draw_box(ax1, 6, 14.8, 5, 1.4, 'MessageBus.inbound\n(Channel → Agent)', C_BUS, fontsize=9)
draw_box(ax1, 14, 14.8, 5, 1.4, 'MessageBus.outbound\n(Agent → Channel)', C_BUS, fontsize=9)

# AgentLoop <-> MessageBus
draw_arrow(ax1, 8, 15.5, 8.5, 16.9, color='#333', connectionstyle="arc3,rad=-0.2")
draw_arrow(ax1, 12, 16.9, 12.5, 15.5, color='#333', connectionstyle="arc3,rad=-0.2")

# ==================== 支撑服务层 ====================
draw_dashed_box(ax1, 10, 12.0, 18, 3.2, 'SUPPORT SERVICES', C_SUPPORT)

draw_box(ax1, 3.5, 12.5, 3.2, 1.3, 'MemoryStore\n(Dream)', C_SUPPORT, fontsize=9)
draw_box(ax1, 7.5, 12.5, 3.2, 1.3, 'SkillsLoader\n(SKILL.md)', C_SUPPORT, fontsize=9)
draw_box(ax1, 11.5, 12.5, 3.2, 1.3, 'SubagentMgr\n(Sub Agents)', C_SUPPORT, fontsize=9)
draw_box(ax1, 15.5, 12.5, 3.2, 1.3, 'CronService\n(Scheduler)', C_SUPPORT, fontsize=9)

draw_box(ax1, 7.5, 10.8, 3.2, 1.2, 'Heartbeat\nService', C_SUPPORT, fontsize=8)
draw_box(ax1, 11.5, 10.8, 3.2, 1.2, 'AutoCompact\n(Context)', C_SUPPORT, fontsize=8)
draw_box(ax1, 15.5, 10.8, 3.2, 1.2, 'GitStore\n(Git Backend)', C_SUPPORT, fontsize=8)

# 支撑服务 -> AgentLoop
draw_arrow(ax1, 5, 13.15, 8, 17.1, color='#777', connectionstyle="arc3,rad=0.15", lw=1)
draw_arrow(ax1, 7.5, 13.15, 9, 17.1, color='#777', lw=1)
draw_arrow(ax1, 11.5, 13.15, 11, 17.1, color='#777', lw=1)
draw_arrow(ax1, 15.5, 13.15, 12.5, 17.1, color='#777', connectionstyle="arc3,rad=-0.1", lw=1)

# ==================== LLM 提供商层 ====================
draw_dashed_box(ax1, 4.5, 8.2, 8.5, 3.0, 'LLM PROVIDERS', C_PROVIDER)

draw_box(ax1, 3, 9.2, 3.5, 1.2, 'OpenAICompat\nProvider', '#ffeaa7', text_color='#2d3436', fontsize=9)
draw_box(ax1, 7, 9.2, 3.5, 1.2, 'Anthropic\nProvider', '#ffeaa7', text_color='#2d3436', fontsize=9)
draw_box(ax1, 3, 7.6, 3.5, 1.0, 'AzureOpenAI\nProvider', '#ffeaa7', text_color='#2d3436', fontsize=8)
draw_box(ax1, 7, 7.6, 3.5, 1.0, 'Registry\n(30+ Providers)', '#ffeaa7', text_color='#2d3436', fontsize=8)

# AgentRunner -> LLM
draw_arrow(ax1, 4.5, 17.1, 4.5, 9.8, color='#777', connectionstyle="arc3,rad=0.1", lw=1)

# ==================== 工具层 ====================
draw_dashed_box(ax1, 13, 8.2, 8.5, 3.0, 'TOOLS', C_TOOL)

draw_box(ax1, 11, 9.2, 2.5, 1.2, 'FileSystem\nTools', '#ff7675', fontsize=8)
draw_box(ax1, 14, 9.2, 2.5, 1.2, 'WebSearch\n& Fetch', '#ff7675', fontsize=8)
draw_box(ax1, 17, 9.2, 2.5, 1.2, 'Shell\nExec', '#ff7675', fontsize=8)

draw_box(ax1, 10.5, 7.6, 2.5, 1.0, 'Search\n(Grep/Glob)', '#ff7675', fontsize=8)
draw_box(ax1, 13.5, 7.6, 2.5, 1.0, 'Message\nTool', '#ff7675', fontsize=8)
draw_box(ax1, 16.5, 7.6, 2.5, 1.0, 'MCP\nTools', '#ff7675', fontsize=8)
draw_box(ax1, 19, 7.6, 1.5, 1.0, '...', '#ff7675', fontsize=10)

# ToolRegistry -> Tools
draw_arrow(ax1, 13.5, 17.1, 14.5, 9.8, color='#777', connectionstyle="arc3,rad=-0.1", lw=1)

# ==================== 通道管理层 ====================
draw_dashed_box(ax1, 10, 4.5, 18, 3.0, 'CHANNEL MANAGER', C_CHANNEL)

draw_box(ax1, 10, 5.5, 5, 1.6, 'ChannelManager\n(Lifecycle + Dispatch)', C_CHANNEL, fontsize=10)

draw_box(ax1, 3.5, 4.0, 2.2, 1.0, 'Telegram', '#a29bfe', text_color='#2d3436', fontsize=8)
draw_box(ax1, 6, 4.0, 2.2, 1.0, 'Discord', '#a29bfe', text_color='#2d3436', fontsize=8)
draw_box(ax1, 8.5, 4.0, 2.2, 1.0, 'WeChat', '#a29bfe', text_color='#2d3436', fontsize=8)
draw_box(ax1, 11, 4.0, 2.2, 1.0, 'Feishu', '#a29bfe', text_color='#2d3436', fontsize=8)
draw_box(ax1, 13.5, 4.0, 2.2, 1.0, 'Slack', '#a29bfe', text_color='#2d3436', fontsize=8)
draw_box(ax1, 16, 4.0, 2.2, 1.0, 'WebSocket', '#a29bfe', text_color='#2d3436', fontsize=8)
draw_box(ax1, 18.5, 4.0, 1.8, 1.0, '...', '#a29bfe', text_color='#2d3436', fontsize=10)

# ChannelManager <-> MessageBus
draw_arrow(ax1, 8, 5.5, 7.5, 14.1, color='#333', connectionstyle="arc3,rad=0.15", lw=1.2)
draw_arrow(ax1, 13, 14.1, 12.5, 5.5, color='#333', connectionstyle="arc3,rad=0.15", lw=1.2)

# ChannelManager -> Channels
for x in [3.5, 6, 8.5, 11, 13.5, 16, 18.5]:
    draw_arrow(ax1, x, 4.5, x, 3.0, color='#555', lw=1)

# ==================== 外部系统集成层 ====================
draw_dashed_box(ax1, 10, 1.8, 18, 2.4, 'EXTERNAL INTEGRATIONS', C_EXTERNAL)

draw_box(ax1, 3, 1.8, 2.5, 1.2, 'WebUI\n(React)', C_EXTERNAL, fontsize=9)
draw_box(ax1, 6.5, 1.8, 2.5, 1.2, 'Bridge\n(Node.js)', C_EXTERNAL, fontsize=9)
draw_box(ax1, 10, 1.8, 2.5, 1.2, 'WhatsApp\n(Baileys)', C_EXTERNAL, fontsize=9)
draw_box(ax1, 13.5, 1.8, 2.5, 1.2, 'OpenAI\nAPI', C_EXTERNAL, fontsize=9)
draw_box(ax1, 17, 1.8, 2.5, 1.2, 'Anthropic\nAPI', C_EXTERNAL, fontsize=9)

# 外部 -> 通道/提供商
draw_arrow(ax1, 3, 2.4, 3, 3.3, color='#888', lw=1)
draw_arrow(ax1, 6.5, 2.4, 6.5, 3.3, color='#888', lw=1)
draw_arrow(ax1, 10, 2.4, 10, 3.3, color='#888', lw=1)
draw_arrow(ax1, 13.5, 2.4, 5.5, 7.1, color='#888', lw=1, connectionstyle="arc3,rad=0.1")
draw_arrow(ax1, 17, 2.4, 8, 7.1, color='#888', lw=1, connectionstyle="arc3,rad=0.1")

# ==================== 图例 ====================
legend_items = [
    (C_ENTRY, 'Entry Points'),
    (C_CORE, 'Core Engine'),
    ('#0984e3', 'Agent Loop'),
    (C_BUS, 'Message Bus'),
    (C_SUPPORT, 'Support Services'),
    (C_PROVIDER, 'LLM Providers'),
    (C_TOOL, 'Tool Layer'),
    (C_CHANNEL, 'Channel Layer'),
    (C_EXTERNAL, 'External Systems'),
]

for i, (color, label) in enumerate(legend_items):
    row = i // 3
    col = i % 3
    lx = 2.5 + col * 5.5
    ly = 0.5 - row * 0.5
    ax1.add_patch(FancyBboxPatch((lx - 0.15, ly - 0.12), 0.3, 0.24,
                                  boxstyle="round,pad=0.01,rounding_size=0.05",
                                  facecolor=color, edgecolor='#333', linewidth=0.8, zorder=5))
    ax1.text(lx + 0.3, ly, label, ha='left', va='center', fontsize=9, color='#333', zorder=5)

plt.tight_layout()
fig1.savefig('yandali/nanobot_system_architecture.png', dpi=200, bbox_inches='tight',
             facecolor='#fafafa', edgecolor='none')
fig1.savefig('yandali/nanobot_system_architecture.svg', bbox_inches='tight',
             facecolor='#fafafa', edgecolor='none')
print("图 1 已保存: nanobot_system_architecture.png / .svg")

# =============================================================================
# 图 2: Agent 核心内部架构图
# =============================================================================
fig2, ax2 = plt.subplots(figsize=(18, 20))
ax2.set_xlim(0, 18)
ax2.set_ylim(0, 20)
ax2.set_aspect('equal')
ax2.axis('off')
ax2.set_facecolor('#fafafa')
fig2.patch.set_facecolor('#fafafa')

ax2.text(9, 19.5, 'Agent Core Internal Architecture', ha='center', va='center',
         fontsize=22, fontweight='bold', color='#1a1a2e')
ax2.text(9, 19.1, 'Detailed Component Diagram of the Agent Loop', ha='center', va='center',
         fontsize=12, color='#555555')

# AgentLoop 中心
draw_box(ax2, 9, 16.5, 6, 2.0, 'AgentLoop\n(Main Event Loop)', '#0984e3', fontsize=13, radius=0.08)

# AgentRunner
draw_box(ax2, 5, 14.0, 4.5, 1.6, 'AgentRunner\n(Tool Call Executor)', '#74b9ff', text_color='#2d3436', fontsize=10, radius=0.06)
draw_arrow(ax2, 7, 15.5, 7.5, 15.5, color='#333', lw=1.5)

# ContextBuilder
draw_box(ax2, 13, 14.0, 4.5, 1.6, 'ContextBuilder\n(System Prompt + History)', '#74b9ff', text_color='#2d3436', fontsize=10, radius=0.06)
draw_arrow(ax2, 11, 15.5, 10.5, 15.5, color='#333', lw=1.5)

# ContextBuilder 子组件
ctx_children = [
    (9.5, 12.0, 'MemoryStore', 'Read/Write\nMemories'),
    (13, 12.0, 'SkillsLoader', 'Load\nSKILL.md'),
    (16.5, 12.0, 'SessionManager', 'JSONL\nPersistence'),
]
for x, y, title, desc in ctx_children:
    draw_box(ax2, x, y, 2.8, 1.4, f'{title}\n{desc}', '#fdcb6e', text_color='#2d3436', fontsize=8, radius=0.04)
    draw_arrow(ax2, x, 12.7, 13 - (13-x)*0.3, 13.2, color='#777', lw=1)

# AgentRunner 子组件
runner_children = [
    (2.5, 12.0, 'LLMProvider', 'Chat /\nStream'),
    (6, 12.0, 'ToolRegistry', 'Execute\nTools'),
    (9.5, 9.5, 'CompositeHook', 'Lifecycle\nHooks'),
]
for x, y, title, desc in runner_children:
    if title == 'CompositeHook':
        draw_box(ax2, x, y, 2.8, 1.4, f'{title}\n{desc}', '#fdcb6e', text_color='#2d3436', fontsize=8, radius=0.04)
        draw_arrow(ax2, 7, 13.2, x-0.5, y+0.7, color='#777', lw=1)
    else:
        draw_box(ax2, x, y, 2.8, 1.4, f'{title}\n{desc}', '#fdcb6e', text_color='#2d3436', fontsize=8, radius=0.04)
        draw_arrow(ax2, x + (1.5 if x < 5 else -1), 12.7, 5 - (5-x)*0.3, 13.2, color='#777', lw=1)

# ToolRegistry -> Tools
tools = [
    (2, 9.5, 'ReadFile'),
    (4.5, 9.5, 'WriteFile'),
    (7, 9.5, 'EditFile'),
    (2, 8.0, 'Exec'),
    (4.5, 8.0, 'WebSearch'),
    (7, 8.0, 'WebFetch'),
    (2, 6.5, 'Grep'),
    (4.5, 6.5, 'Glob'),
    (7, 6.5, 'Message'),
    (2, 5.0, 'Notebook'),
    (4.5, 5.0, 'Cron'),
    (7, 5.0, 'MCP'),
]
for x, y, name in tools:
    draw_box(ax2, x, y, 2.2, 1.0, name, '#ff7675', fontsize=8, radius=0.03)
    draw_arrow(ax2, x, y+0.5, 5.5, 11.3, color='#999', lw=0.8, connectionstyle="arc3,rad=0.1")

# LLM Provider 详情
providers = [
    (13, 9.5, 'OpenAICompat'),
    (15.5, 9.5, 'Anthropic'),
    (13, 8.0, 'AzureOpenAI'),
    (15.5, 8.0, 'OpenAICodex'),
    (13, 6.5, 'GitHubCopilot'),
    (15.5, 6.5, '...'),
]
for x, y, name in providers:
    draw_box(ax2, x, y, 2.2, 1.0, name, '#ffeaa7', text_color='#2d3436', fontsize=8, radius=0.03)
    draw_arrow(ax2, x, y+0.5, 3.5, 11.3, color='#999', lw=0.8, connectionstyle="arc3,rad=-0.1")

# 执行流程标注
flow_steps = [
    (1, 16.5, '1. Receive'),
    (1, 14.8, '2. Build\nContext'),
    (1, 12.5, '3. Call LLM'),
    (1, 9.5, '4. Execute\nTools'),
    (1, 6.5, '5. Stream\nOutput'),
]
for x, y, text in flow_steps:
    ax2.text(x, y, text, ha='center', va='center', fontsize=9, color='#555',
             fontweight='bold', bbox=dict(boxstyle='round,pad=0.3', facecolor='#eee', edgecolor='#ccc'))

# 循环箭头
ax2.annotate('', xy=(2.5, 16.2), xytext=(2.5, 5.0),
            arrowprops=dict(arrowstyle='->', color='#b2bec3', lw=2,
                           connectionstyle="arc3,rad=-0.5"), zorder=1)
ax2.text(0.8, 10.5, 'Iterative\nLoop', ha='center', va='center', fontsize=9,
         color='#b2bec3', fontweight='bold', rotation=90)

plt.tight_layout()
fig2.savefig('yandali/nanobot_agent_core_architecture.png', dpi=200, bbox_inches='tight',
             facecolor='#fafafa', edgecolor='none')
fig2.savefig('yandali/nanobot_agent_core_architecture.svg', bbox_inches='tight',
             facecolor='#fafafa', edgecolor='none')
print("图 2 已保存: nanobot_agent_core_architecture.png / .svg")

# =============================================================================
# 图 3: 数据流图
# =============================================================================
fig3, ax3 = plt.subplots(figsize=(18, 14))
ax3.set_xlim(0, 18)
ax3.set_ylim(0, 14)
ax3.set_aspect('equal')
ax3.axis('off')
ax3.set_facecolor('#fafafa')
fig3.patch.set_facecolor('#fafafa')

ax3.text(9, 13.5, 'Data Flow Diagram', ha='center', va='center',
         fontsize=22, fontweight='bold', color='#1a1a2e')
ax3.text(9, 13.1, 'Message Flow from User Input to Agent Response', ha='center', va='center',
         fontsize=12, color='#555555')

# 用户
ax3.add_patch(plt.Circle((1.5, 10), 0.6, facecolor='#636e72', edgecolor='#333', linewidth=1.5, zorder=3))
ax3.text(1.5, 10, 'User', ha='center', va='center', fontsize=9, color='white', fontweight='bold', zorder=4)

# 通道适配器
draw_box(ax3, 4.5, 10, 3, 1.2, 'Channel Adapter\n(Telegram/Discord/...)', '#6c5ce7', fontsize=9)
draw_arrow(ax3, 2.1, 10, 3, 10, color='#333', lw=1.5)

# MessageBus inbound
draw_box(ax3, 9, 10, 3.5, 1.2, 'MessageBus.inbound\n(asyncio.Queue)', '#00b894', fontsize=9)
draw_arrow(ax3, 6, 10, 7.25, 10, color='#333', lw=1.5)

# AgentLoop
draw_box(ax3, 13.5, 10, 3.5, 1.2, 'AgentLoop.process\n(Direct Message)', '#0984e3', fontsize=9)
draw_arrow(ax3, 10.75, 10, 11.75, 10, color='#333', lw=1.5)

# 内部分支
branches = [
    (9, 7.5, 'ContextBuilder', 'System Prompt +\nMemory + Skills'),
    (13.5, 7.5, 'ToolRegistry', 'Available Tools\n(Function Calling)'),
    (4.5, 7.5, 'SessionManager', 'Message History\n(JSONL)'),
]
for x, y, title, desc in branches:
    draw_box(ax3, x, y, 3.5, 1.4, f'{title}\n{desc}', '#74b9ff', text_color='#2d3436', fontsize=9, radius=0.04)

draw_arrow(ax3, 13.5, 9.4, 13.5, 8.2, color='#555', lw=1.2)
draw_arrow(ax3, 12.5, 9.4, 10, 8.2, color='#555', lw=1.2)
draw_arrow(ax3, 12, 9.4, 6.25, 8.2, color='#555', lw=1.2)

# LLM Provider
draw_box(ax3, 9, 5, 3.5, 1.2, 'LLMProvider.chat()\n(OpenAI/Anthropic/...)', '#fdcb6e', text_color='#2d3436', fontsize=9)
draw_arrow(ax3, 9, 6.8, 9, 5.6, color='#555', lw=1.2)
draw_arrow(ax3, 13.5, 6.8, 10.75, 5.6, color='#555', lw=1.2, connectionstyle="arc3,rad=-0.15")

# 工具执行 / 流式输出
draw_box(ax3, 5, 5, 3, 1.2, 'Tool Execution\n(Shell/File/Web)', '#ff7675', fontsize=9)
draw_box(ax3, 13, 5, 3, 1.2, 'Stream Output\n(AgentHook)', '#ff7675', fontsize=9)

draw_arrow(ax3, 9, 4.4, 6.5, 5.0, color='#555', lw=1.2, connectionstyle="arc3,rad=0.1")
ax3.annotate('', xy=(13, 5.0), xytext=(10.5, 4.4),
            arrowprops=dict(arrowstyle='->', color='#555', lw=1.2,
                           connectionstyle="arc3,rad=-0.1"), zorder=2)

# 循环箭头 (Tool result -> LLM)
ax3.annotate('', xy=(8, 5.6), xytext=(6, 5.6),
            arrowprops=dict(arrowstyle='->', color='#b2bec3', lw=1.5,
                           connectionstyle="arc3,rad=0.3"), zorder=1)
ax3.text(7, 6.2, 'Tool Result', ha='center', va='center', fontsize=8, color='#b2bec3', fontweight='bold')

# MessageBus outbound
draw_box(ax3, 9, 2.5, 3.5, 1.2, 'MessageBus.outbound\n(asyncio.Queue)', '#00b894', fontsize=9)
draw_arrow(ax3, 6.5, 4.4, 8, 3.1, color='#555', lw=1.2, connectionstyle="arc3,rad=-0.1")
draw_arrow(ax3, 13, 4.4, 11.5, 3.1, color='#555', lw=1.2, connectionstyle="arc3,rad=0.1")

# ChannelManager dispatch
draw_box(ax3, 4.5, 2.5, 3, 1.2, 'ChannelManager\n.dispatch()', '#6c5ce7', fontsize=9)
draw_arrow(ax3, 7.25, 2.5, 6, 2.5, color='#333', lw=1.5)

# 用户接收
ax3.add_patch(plt.Circle((1.5, 2.5), 0.6, facecolor='#636e72', edgecolor='#333', linewidth=1.5, zorder=3))
ax3.text(1.5, 2.5, 'User', ha='center', va='center', fontsize=9, color='white', fontweight='bold', zorder=4)
draw_arrow(ax3, 3, 2.5, 2.1, 2.5, color='#333', lw=1.5)

# 流式标注
ax3.text(16.5, 5, 'Streaming\n(deltas)', ha='center', va='center', fontsize=8,
         color='#d63031', fontweight='bold',
         bbox=dict(boxstyle='round,pad=0.2', facecolor='#ffebee', edgecolor='#d63031'))

# 步骤编号
steps = [
    (3.2, 10.6, '①'),
    (7.5, 10.6, '②'),
    (11.2, 10.6, '③'),
    (10.2, 5.6, '④'),
    (6.2, 5.6, '⑤'),
    (7.8, 2.5, '⑥'),
]
for x, y, num in steps:
    ax3.text(x, y, num, ha='center', va='center', fontsize=11, color='white', fontweight='bold',
             bbox=dict(boxstyle='circle,pad=0.15', facecolor='#e17055', edgecolor='none'))

plt.tight_layout()
fig3.savefig('yandali/nanobot_data_flow.png', dpi=200, bbox_inches='tight',
             facecolor='#fafafa', edgecolor='none')
fig3.savefig('yandali/nanobot_data_flow.svg', bbox_inches='tight',
             facecolor='#fafafa', edgecolor='none')
print("图 3 已保存: nanobot_data_flow.png / .svg")

# =============================================================================
# 图 4: 技术栈分层图
# =============================================================================
fig4, ax4 = plt.subplots(figsize=(16, 12))
ax4.set_xlim(0, 16)
ax4.set_ylim(0, 12)
ax4.set_aspect('equal')
ax4.axis('off')
ax4.set_facecolor('#fafafa')
fig4.patch.set_facecolor('#fafafa')

ax4.text(8, 11.5, 'Technology Stack', ha='center', va='center',
         fontsize=22, fontweight='bold', color='#1a1a2e')

layers = [
    (11.0, 1.8, 'User Interface Layer', '#2d3436', [
        'CLI (Typer)', 'WebUI (React + Vite)', 'OpenAI Compatible API'
    ]),
    (9.0, 1.8, 'Communication Layer', '#6c5ce7', [
        'Telegram', 'Discord', 'WeChat', 'Feishu', 'Slack', 'WhatsApp (Bridge)',
        'WebSocket', 'QQ', 'Email', 'Matrix', 'DingTalk', 'MoChat', 'MSTeams', 'WeCom'
    ]),
    (7.0, 1.8, 'Agent Core Layer', '#0984e3', [
        'AgentLoop', 'AgentRunner', 'ContextBuilder', 'MessageBus',
        'ToolRegistry', 'AgentHook', 'SubagentManager'
    ]),
    (5.0, 1.8, 'Service Layer', '#e17055', [
        'MemoryStore (Dream)', 'SkillsLoader', 'SessionManager',
        'CronService', 'HeartbeatService', 'AutoCompact', 'GitStore'
    ]),
    (3.0, 1.8, 'Integration Layer', '#fdcb6e', [
        'OpenAI SDK', 'Anthropic SDK', 'Azure OpenAI', 'Baileys (WhatsApp)',
        'aiohttp', 'WebSearch APIs'
    ]),
    (1.0, 1.8, 'Infrastructure Layer', '#636e72', [
        'Python 3.11+', 'asyncio', 'Pydantic', 'Loguru',
        'Node.js 20+ (Bridge)', 'TypeScript', 'Docker'
    ]),
]

colors = ['#2d3436', '#6c5ce7', '#0984e3', '#e17055', '#fdcb6e', '#636e72']
for i, (y, h, title, color, items) in enumerate(layers):
    # 层背景
    ax4.add_patch(FancyBboxPatch((0.5, y - h/2), 15, h,
                                  boxstyle="round,pad=0.02,rounding_size=0.05",
                                  facecolor=color, edgecolor='none', alpha=0.1, zorder=1))
    ax4.add_patch(FancyBboxPatch((0.5, y + h/2 - 0.35), 15, 0.35,
                                  boxstyle="round,pad=0.01,rounding_size=0.02",
                                  facecolor=color, edgecolor='none', alpha=0.3, zorder=2))
    ax4.text(1.2, y + h/2 - 0.18, title, ha='left', va='center',
             fontsize=11, fontweight='bold', color=color, zorder=3)

    # 模块框
    n_items = len(items)
    box_w = min(2.2, 13.5 / max(n_items, 1))
    start_x = 8 - (n_items * box_w) / 2 + box_w/2
    for j, item in enumerate(items):
        bx = start_x + j * box_w
        draw_box(ax4, bx, y - 0.05, box_w - 0.15, 0.9, item, color, fontsize=7.5, radius=0.02)

plt.tight_layout()
fig4.savefig('yandali/nanobot_tech_stack.png', dpi=200, bbox_inches='tight',
             facecolor='#fafafa', edgecolor='none')
fig4.savefig('yandali/nanobot_tech_stack.svg', bbox_inches='tight',
             facecolor='#fafafa', edgecolor='none')
print("图 4 已保存: nanobot_tech_stack.png / .svg")

# =============================================================================
# 图 5: 模块依赖关系图 (NetworkX)
# =============================================================================
import networkx as nx

fig5, ax5 = plt.subplots(figsize=(18, 16))
ax5.set_facecolor('#fafafa')
fig5.patch.set_facecolor('#fafafa')

G = nx.DiGraph()

# 节点分类
categories = {
    'entry': ['CLI', 'API Server', 'Gateway', 'Python SDK'],
    'core': ['Nanobot', 'AgentLoop', 'AgentRunner', 'ContextBuilder'],
    'bus': ['MessageBus'],
    'support': ['MemoryStore', 'SkillsLoader', 'SessionManager', 'CronService', 'HeartbeatService'],
    'provider': ['LLMProvider', 'OpenAICompat', 'AnthropicProvider'],
    'tools': ['ToolRegistry', 'FileSystemTools', 'ShellExec', 'WebSearch', 'MCP'],
    'channel': ['ChannelManager', 'Telegram', 'Discord', 'WeChat', 'WebSocket', 'WhatsApp'],
    'external': ['WebUI', 'Bridge', 'OpenAI API', 'Anthropic API'],
}

all_nodes = [n for nodes in categories.values() for n in nodes]
G.add_nodes_from(all_nodes)

# 边定义
edges = [
    # 入口 -> 核心
    ('CLI', 'Nanobot'), ('API Server', 'Nanobot'), ('Gateway', 'Nanobot'), ('Python SDK', 'Nanobot'),
    # 核心内部
    ('Nanobot', 'AgentLoop'),
    ('AgentLoop', 'AgentRunner'), ('AgentLoop', 'ContextBuilder'), ('AgentLoop', 'MessageBus'),
    ('AgentRunner', 'LLMProvider'), ('AgentRunner', 'ToolRegistry'),
    ('ContextBuilder', 'MemoryStore'), ('ContextBuilder', 'SkillsLoader'), ('ContextBuilder', 'SessionManager'),
    # 总线 <-> 通道
    ('MessageBus', 'ChannelManager'), ('ChannelManager', 'MessageBus'),
    # 通道 -> 外部
    ('ChannelManager', 'Telegram'), ('ChannelManager', 'Discord'), ('ChannelManager', 'WeChat'),
    ('ChannelManager', 'WebSocket'), ('ChannelManager', 'WhatsApp'),
    # 外部 -> 通道/提供商
    ('WebUI', 'WebSocket'), ('Bridge', 'WhatsApp'),
    ('OpenAI API', 'OpenAICompat'), ('Anthropic API', 'AnthropicProvider'),
    # 支撑
    ('AgentLoop', 'CronService'), ('AgentLoop', 'HeartbeatService'),
    # 工具
    ('ToolRegistry', 'FileSystemTools'), ('ToolRegistry', 'ShellExec'),
    ('ToolRegistry', 'WebSearch'), ('ToolRegistry', 'MCP'),
    # 提供商
    ('LLMProvider', 'OpenAICompat'), ('LLMProvider', 'AnthropicProvider'),
]

G.add_edges_from(edges)

# 布局
pos = nx.spring_layout(G, k=2.5, iterations=100, seed=42)

# 手动调整位置使图更美观
pos['Nanobot'] = (0, 0.3)
pos['AgentLoop'] = (0, -0.3)
pos['CLI'] = (-1.5, 0.8)
pos['API Server'] = (-0.5, 0.8)
pos['Gateway'] = (0.5, 0.8)
pos['Python SDK'] = (1.5, 0.8)
pos['AgentRunner'] = (-0.8, -0.8)
pos['ContextBuilder'] = (0.8, -0.8)
pos['MessageBus'] = (0, -1.5)
pos['ChannelManager'] = (0, -2.3)
pos['LLMProvider'] = (-1.5, -1.3)
pos['ToolRegistry'] = (1.5, -1.3)
pos['MemoryStore'] = (1.3, -0.3)
pos['SkillsLoader'] = (1.8, -0.5)
pos['SessionManager'] = (2.0, -0.1)
pos['CronService'] = (-1.8, -0.1)
pos['HeartbeatService'] = (-2.0, -0.5)
pos['Telegram'] = (-1.2, -3.0)
pos['Discord'] = (-0.4, -3.0)
pos['WeChat'] = (0.4, -3.0)
pos['WebSocket'] = (1.2, -3.0)
pos['WhatsApp'] = (2.0, -3.0)
pos['WebUI'] = (1.2, -3.8)
pos['Bridge'] = (2.0, -3.8)
pos['OpenAICompat'] = (-1.5, -2.0)
pos['AnthropicProvider'] = (-2.2, -1.8)
pos['OpenAI API'] = (-1.5, -2.8)
pos['Anthropic API'] = (-2.5, -2.5)
pos['FileSystemTools'] = (2.5, -0.8)
pos['ShellExec'] = (2.8, -1.2)
pos['WebSearch'] = (2.5, -1.6)
pos['MCP'] = (2.2, -2.0)

# 颜色映射
color_map = {
    'entry': '#2d3436', 'core': '#0984e3', 'bus': '#00b894',
    'support': '#e17055', 'provider': '#fdcb6e', 'tools': '#ff7675',
    'channel': '#6c5ce7', 'external': '#636e72'
}

node_colors = []
for node in G.nodes():
    for cat, nodes in categories.items():
        if node in nodes:
            node_colors.append(color_map[cat])
            break
    else:
        node_colors.append('#999')

# 节点大小
node_sizes = [3000 if node in ['AgentLoop', 'Nanobot', 'MessageBus', 'ChannelManager'] else 2000 for node in G.nodes()]

nx.draw_networkx_edges(G, pos, ax=ax5, arrowsize=15, arrowstyle='->',
                       edge_color='#888888', width=1.2, alpha=0.7,
                       connectionstyle='arc3,rad=0.1', node_size=node_sizes)

nx.draw_networkx_nodes(G, pos, ax=ax5, node_color=node_colors,
                       node_size=node_sizes, alpha=0.9,
                       edgecolors='#333', linewidths=1.5)

# 标签
labels = {n: n for n in G.nodes()}
nx.draw_networkx_labels(G, pos, labels, ax=ax5, font_size=8,
                        font_weight='bold', font_color='white')

ax5.set_title('Module Dependency Graph', fontsize=20, fontweight='bold', color='#1a1a2e', pad=20)

# 图例
legend_patches = [mpatches.Patch(color=color, label=cat.title())
                  for cat, color in color_map.items()]
ax5.legend(handles=legend_patches, loc='upper left', fontsize=10, framealpha=0.9)

ax5.set_xlim(-3.5, 3.5)
ax5.set_ylim(-4.5, 1.5)
ax5.axis('off')

plt.tight_layout()
fig5.savefig('yandali/nanobot_dependency_graph.png', dpi=200, bbox_inches='tight',
             facecolor='#fafafa', edgecolor='none')
fig5.savefig('yandali/nanobot_dependency_graph.svg', bbox_inches='tight',
             facecolor='#fafafa', edgecolor='none')
print("图 5 已保存: nanobot_dependency_graph.png / .svg")

print("\n✅ 所有架构图已生成完毕！")
print("📁 输出目录: yandali/")
print("📄 文件列表:")
print("   1. nanobot_system_architecture.png/svg     - 整体系统架构")
print("   2. nanobot_agent_core_architecture.png/svg - Agent 核心内部架构")
print("   3. nanobot_data_flow.png/svg               - 数据流图")
print("   4. nanobot_tech_stack.png/svg              - 技术栈分层")
print("   5. nanobot_dependency_graph.png/svg        - 模块依赖关系")
