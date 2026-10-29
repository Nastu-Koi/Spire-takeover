# Spire Takeover：让模型接管 Steam 版《杀戮尖塔 2》

从 [Spire-model](../Spire-model) 单独拆出的实机接管功能，只保留三样东西：

| 目录 | 内容 |
| --- | --- |
| `release/SpireTakeover/` | 已编译好的游戏 Mod（`SpireTakeover.dll` + `SpireTakeover.json`），直接放进游戏的 `mods/` |
| `spire_takeover/` | Python 控制端：读 Mod 的快照、拼成模型的输入、推理、把动作交回游戏 |
| `checkpoint/` | 模型检查点（只含推理用的 `manifest.json` 与 `weights.pt`，约 85 MB） |
| `mod/` | Mod 源码与构建脚本，游戏更新或要改 Mod 时才用 |
| `tests/` | 离线测试（含用自带检查点走一遍桥接的端到端测试） |

训练、采样、无头引擎、求解器都不在这里。

适配：游戏 **0.111.0**，单人对局，任何角色、任何难度；桥接协议 `steam-live-v5`。

自带检查点：Spire-model 的 `checkpoints/rl-20261023/train/fight-rl-12/iteration-0004`（policy_version 169），开发集 A10 胜率 17.0%（500 局，2026-10-28）。

## 1. 安装 Mod

**方式 A：用编译好的（推荐）**

把 `release/SpireTakeover` 整个文件夹复制到游戏目录的 `mods/` 下，得到：

```
<游戏目录>/mods/SpireTakeover/SpireTakeover.dll
<游戏目录>/mods/SpireTakeover/SpireTakeover.json
```

游戏目录在 Steam 里右键游戏 →“管理”→“浏览本地文件”。游戏目录里若还有旧名的 `mods/RunRecorder`，先移走，免得两个 Mod 同时加载。

**方式 B：从源码构建**（需要 .NET 9 SDK；游戏更新后要这样重编）

```bash
python mod/install.py --game-dir "/mnt/d/SteamLibrary/steamapps/common/Slay the Spire 2" --install
```

脚本读取游戏原始的 `sts2.dll`、`GodotSharp.dll`、`0Harmony.dll` 构建并安装到 `mods/SpireTakeover`，被替换的旧文件备份在 `build/takeover-backups/<时间>/`。不加 `--install` 只构建（产物在 `mod/bin/Release/net9.0/`）。重编后把 DLL 拷回 `release/SpireTakeover/`，保持 `release/` 是最新的。

启动游戏（游戏询问是否加载 Mod 时选加载），Mod 列表里会出现“模型接管 / Spire Takeover”。Mod 加载后会建立桥接目录：

- Windows：`%APPDATA%\SlayTheSpire2\spire_takeover\bridge`
- 从 WSL 看：`/mnt/c/Users/<用户名>/AppData/Roaming/SlayTheSpire2/spire_takeover/bridge`

## 2. 准备 Python

需要 Python 3.11 及以上（用到 `datetime.UTC`）和 PyTorch（有 NVIDIA 显卡就装 CUDA 版，没有也能用 CPU 跑，单步推理足够快）。除 torch 及 pip 随它装上的依赖外，不需要其它第三方库（numpy、tqdm 都不需要）；跑测试另需 pytest。实测版本：Python 3.11.16、torch 2.14.0；更低的 torch 没测过，至少要 2.4。构建 Mod（方式 B）另需 .NET 9 SDK，用编译好的 Mod 则不需要。

在 WSL / Linux 里，用已有的 Spire-model 环境即可：

```bash
/home/nastukoi/miniconda3/envs/sts2/bin/python -m spire_takeover --help
```

在 Windows 上直接跑（不经过 WSL）：按 [pytorch.org](https://pytorch.org/get-started/locally/) 装好 torch，然后在本目录执行 `python -m spire_takeover --help`。

## 3. 开始接管

在本目录（`Spire-takeover/`）下运行：

```bash
python -m spire_takeover --run-for 8h
```

- 桥接目录自动查找（Windows 的 `%APPDATA%`、WSL 下的 `/mnt/c/Users/*/AppData/Roaming`、Linux 的 `~/.local/share` 与 Proton 前缀）；找不到或找到多个时报错，此时用 `--bridge-dir` 指定。
- 默认用自带的 `checkpoint/`；换检查点用 `--checkpoint <目录>`（目录里要有 `manifest.json` 和权重文件，Spire-model 的任何检查点目录都可以直接给）。
- 有 CUDA 时默认用 GPU，否则 CPU；`--device cpu` 强制 CPU。
- `--run-for` 常驻时长（`8h`、`45m`、`90s`；不给则直到 Ctrl-C），`--max-decisions N` 做满 N 步后退出。
- `--compile` 用 torch.compile 编译模型（需要 C++ 编译器，Windows 上是 MSVC；只换来一点速度，默认不开）。

控制端会一直等着游戏：主菜单、动画、你手动操作的阶段都只是等待；一局打完记一笔，接着等下一局。退出时打印局数、胜场、决策数和错误数。同一个桥接目录只能有一个控制端。

## 4. 游戏内的“模型”面板

游戏左下角的“模型”按钮展开控制面板：

- **允许模型接管**：总开关，关掉后模型只看不动。
- **接管战斗 / 接管局外**：分别控制。比如只开“接管战斗”，地图、事件、商店、营火、奖励由你来点。
- **每步间隔（秒）**：放慢模型的操作，方便观看。
- 状态栏、当前决策、最近 20 条决策（含模型的前五排名与概率）。
- 控制端出错时会停下并显示错误，按“重置并重新读取状态”后从当前画面继续。

开关与间隔保存在桥接目录同级的 `settings.json`。

## 5. 记录文件（都在桥接目录里）

| 文件 | 内容 |
| --- | --- |
| `decisions.jsonl` | 每步决策：时间、局、序号、幕、楼层、动作、阶段、摘要、是否由规则控制器执行、模型前五排名 |
| `runs.jsonl` | 每局结束：时间、是否胜利、累计决策数 |
| `errors.jsonl` | 控制端遇到的错误（之后停下等面板重置） |
| `empty-selections.jsonl` | 选牌界面却没给出可选的牌时的整条桥接消息，排查 Mod 用 |

## 6. 常见问题

- **报 “The installed SpireTakeover mod speaks …”**：Mod 与控制端协议版本不一致，重新装 `release/` 里的 Mod（或按方式 B 重编）。
- **报 “Checkpoint was trained with different rule text”**：检查点与 `spire_takeover/data/localization_eng/` 的规则文本不配套；换检查点时要连同 Spire-model 当时的规则文本一起更新。
- **报 “Another model controller is using this bridge”**：已有一个控制端在跑，先关掉它。
- **游戏更新后**：Mod 需要按方式 B 重编；若新版本改了卡牌、遗物等内容，模型的规则文本也会对不上，要等 Spire-model 适配新版本后再从那里同步。

## 7. 从 Spire-model 同步

这里的代码是 Spire-model 的副本，导入名从 `main.` 改成了 `spire_takeover.`，另有几处为单独运行做的改动：检查点加载只保留推理部分、默认不编译模型、文件一律按 UTF-8 读、桥接锁在 Windows 上用 `msvcrt`、命令行自动查找桥接目录。对应关系：

| 这里 | Spire-model |
| --- | --- |
| `spire_takeover/steam/` | `main/steam/` |
| `spire_takeover/encoding/` | `main/encoding/` |
| `spire_takeover/network/{attention,config,model,policy}.py` | `main/network/` 同名文件 |
| `spire_takeover/network/checkpoint.py` | `main/network/checkpoint.py` 的 `load_model` |
| `spire_takeover/env/{clock,control,crystal_rule,treasure_rule,protocol,public_history}.py` | `main/env/` 同名文件 |
| `spire_takeover/data/localization_eng/` | `sts2-cli/localization_eng/` 中规则文本用到的 11 张表 |
| `mod/SpireTakeover/`、`mod/PublicHistory/` | `steam_takeover/SpireTakeover/`、`public_history/` |

## 测试

```bash
python -m pytest -q tests
```

全部离线运行，不需要游戏；`test_end_to_end.py` 用自带检查点在 CPU 上对一条录下的奖励界面消息做一次完整的观察—决策—执行。
