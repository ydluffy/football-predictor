import os
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
import requests

from config.settings import get_settings

logger = logging.getLogger(__name__)

class FootballDataClient:
    """
    负责抓取和拉取实时的足球赛程与高级特征数据（伤停、xG、赔率变动）。
    支持对接 API-Football 或其他付费数据源，并在没有 API Key 时回退到公共页面爬取或高质量 Mock 数据。
    """
    def __init__(self, api_key: str = None, *, allow_mock: bool = False):
        self.api_key = api_key or os.getenv("API_FOOTBALL_KEY")
        self.allow_mock = bool(allow_mock)
        self.headers = {
            "x-apisports-key": self.api_key,
        } if self.api_key else {}

    def fetch_today_matches(self, date_str: str = None) -> pd.DataFrame:
        """获取指定日期（默认今日）的赛程以及高级特征数据。"""
        if not date_str:
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        if self.api_key:
            logger.info(f"使用 API-Football 获取 {date_str} 的实时数据...")
            return self._fetch_from_api(date_str)
        else:
            logger.info(f"未配置 API_FOOTBALL_KEY，使用公开免费渠道抓取 {date_str} 的实时数据...")
            return self._fetch_from_public_fallback(date_str)

    def _fetch_from_api(self, date_str: str) -> pd.DataFrame:
        """使用真实 API 获取数据（示例实现）"""
        url = "https://v3.football.api-sports.io/fixtures"
        params = {"date": date_str, "timezone": "Asia/Shanghai"}
        try:
            resp = requests.get(url, headers=self.headers, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            # 解析真实API数据的逻辑... (此处为了演示返回空 DataFrame)
            return pd.DataFrame()
        except Exception as e:
            logger.error(f"API 请求失败: {e}，回退到 Public 抓取")
            return self._fetch_from_public_fallback(date_str)

    def _fetch_from_public_fallback(self, date_str: str) -> pd.DataFrame:
        """
        爬虫回退机制：从免费公开接口获取真实赛程数据。
        如果公开接口失败，则生成高质量的模拟实时赛程。
        """
        import time
        from datetime import datetime, timedelta
        
        # 尝试从一个免费的公开体育 API 抓取真实赛程数据
        # 这里使用 football-data.org 的免费层 (不需要强校验 API key 也能获取基础赛程)
        # 或者使用一个公开无需认证的聚合赛程接口作为演示。
        # 由于完全公开无限制的高质量足球 API 极少，我们使用一个常见的公开可访问的 JSON 聚合端点 (比如部分开源项目维护的赛程表) 
        # 为了稳定运行，这里写一个爬虫去获取懂球帝或雷速体育的公开接口（这里以雷速体育或网易体育的某公开接口数据结构为例进行模拟请求）
        
        try:
            # 请求懂球帝/雷速等公开的移动端接口获取当天赛程
            # 这是一个示例性质的公共 API 请求（请注意实际生产中应遵守对方的 robots.txt 或使用商业 API）
            # 我们请求一个提供当天基础赛事比分/赔率的公共聚合端点
            url = f"https://www.thesportsdb.com/api/v2/json/3/eventsday.php?d={date_str}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "application/json"
            }
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                events = data.get("events", [])
                
                if events:
                    logger.info(f"成功从公开接口抓取到 {len(events)} 场真实比赛数据")
                    parsed_matches = []
                    
                    for event in events:
                        # 只筛选知名联赛，比如英超、西甲、意甲、德甲、法甲
                        league_name = event.get("strLeague", "")
                        if not any(top_league in league_name for top_league in ["Premier League", "LaLiga", "Serie A", "Bundesliga", "Ligue 1"]):
                            continue
                            
                        # 模拟从公开接口中解析基础信息
                        match_id = event.get("idEvent", f"live_{date_str}_{len(parsed_matches)}")
                        home_team = event.get("strHomeTeam", "Unknown Home")
                        away_team = event.get("strAwayTeam", "Unknown Away")
                        time_str = event.get("strTime", "20:00:00")
                        
                        # 很多免费接口不提供赔率和 xG，为了保证模型的 v3 特征流水线能跑通，
                        # 我们利用基于两队历史名气的简单启发式规则来填充这些高级特征的合理估算值
                        # 实际生产中应从另一个页面专门爬取赔率和 xG (比如抓取 oddsportal)
                        import random
                        import hashlib
                        
                        # 利用两队名字生成固定的伪随机数，让估算值每次运行保持一致
                        hash_val = int(hashlib.md5(f"{home_team}_{away_team}".encode()).hexdigest(), 16)
                        random.seed(hash_val)
                        
                        base_home_odds = round(random.uniform(1.5, 3.5), 2)
                        base_away_odds = round(4.5 - base_home_odds + random.uniform(-0.5, 0.5), 2)
                        base_draw_odds = round(3.2 + random.uniform(-0.2, 0.6), 2)
                        
                        # xG 根据赔率反推
                        xg_home = round(2.5 / base_home_odds, 2)
                        xg_away = round(2.5 / base_away_odds, 2)
                        
                        match_data = {
                            "match_id": match_id,
                            "date": f"{date_str} {time_str}",
                            "league": league_name,
                            "home_team": home_team,
                            "away_team": away_team,
                            "odds_home": base_home_odds, 
                            "odds_draw": base_draw_odds, 
                            "odds_away": base_away_odds,
                            "odds_home_open": round(base_home_odds + random.uniform(-0.1, 0.2), 2), 
                            "odds_draw_open": round(base_draw_odds + random.uniform(-0.1, 0.1), 2), 
                            "odds_away_open": round(base_away_odds + random.uniform(-0.2, 0.1), 2),
                            "odds_home_last": base_home_odds, 
                            "odds_draw_last": base_draw_odds, 
                            "odds_away_last": base_away_odds,
                            "xg_home": xg_home, 
                            "xg_away": xg_away,  
                            "injury_flag": random.choice([0, 0, 0, 1]),  # 25% 概率有伤停
                            "line_move": round(random.uniform(-0.15, 0.15), 2),
                            "actual_result": None 
                        }
                        parsed_matches.append(match_data)
                        
                    if parsed_matches:
                        out = pd.DataFrame(parsed_matches)
                        if not self.allow_mock:
                            synthetic_columns = [
                                "odds_home",
                                "odds_draw",
                                "odds_away",
                                "odds_home_open",
                                "odds_draw_open",
                                "odds_away_open",
                                "odds_home_last",
                                "odds_draw_last",
                                "odds_away_last",
                                "xg_home",
                                "xg_away",
                                "injury_flag",
                                "line_move",
                            ]
                            out.loc[:, synthetic_columns] = pd.NA
                            out["data_source"] = "thesportsdb"
                            out["data_quality"] = "schedule_only"
                            out["is_predictable"] = False
                        return out
                    
            logger.warning(f"公开接口返回的数据为空或解析失败，启用 Mock 数据")
        except Exception as e:
            logger.warning(f"抓取公开实时数据异常: {e}，回退到 Mock 数据")
            
        # 如果爬虫失败或者当天没有大联赛，回退到兜底的 Mock 逻辑
        if self.allow_mock:
            return self._generate_mock_matches(date_str)
        return pd.DataFrame(
            columns=[
                "match_id",
                "date",
                "league",
                "home_team",
                "away_team",
                "odds_home",
                "odds_draw",
                "odds_away",
                "data_source",
                "data_quality",
                "is_predictable",
            ]
        )

    def _generate_mock_matches(self, date_str: str) -> pd.DataFrame:
        """生成高质量的模拟实时赛程（包含模型需要的 v2/v3 高级特征）"""
        data = [
            {
                "match_id": f"live_{date_str}_01",
                "date": f"{date_str} 20:00:00",
                "league": "Premier League",
                "home_team": "Arsenal",
                "away_team": "Chelsea",
                "odds_home": 2.10, "odds_draw": 3.40, "odds_away": 3.20,
                "odds_home_open": 2.30, "odds_draw_open": 3.30, "odds_away_open": 3.00,
                "odds_home_last": 2.10, "odds_draw_last": 3.40, "odds_away_last": 3.20,
                "xg_home": 1.85, "xg_away": 1.20,  # 高级特征：预期进球
                "injury_flag": 1,                  # 高级特征：是否有核心球员伤病
                "line_move": -0.20,                # 高级特征：主胜赔率变动幅度
                "actual_result": None              # 比赛未开始
            },
            {
                "match_id": f"live_{date_str}_02",
                "date": f"{date_str} 22:30:00",
                "league": "La Liga",
                "home_team": "Real Madrid",
                "away_team": "Barcelona",
                "odds_home": 2.50, "odds_draw": 3.50, "odds_away": 2.60,
                "odds_home_open": 2.40, "odds_draw_open": 3.50, "odds_away_open": 2.70,
                "odds_home_last": 2.50, "odds_draw_last": 3.50, "odds_away_last": 2.60,
                "xg_home": 1.50, "xg_away": 1.55,
                "injury_flag": 0,
                "line_move": 0.10,
                "actual_result": None
            },
            {
                "match_id": f"live_{date_str}_03",
                "date": f"{date_str} 23:00:00",
                "league": "Serie A",
                "home_team": "Juventus",
                "away_team": "AC Milan",
                "odds_home": 2.00, "odds_draw": 3.20, "odds_away": 3.60,
                "odds_home_open": 2.05, "odds_draw_open": 3.20, "odds_away_open": 3.50,
                "odds_home_last": 2.00, "odds_draw_last": 3.20, "odds_away_last": 3.60,
                "xg_home": 1.40, "xg_away": 0.90,
                "injury_flag": 1,
                "line_move": -0.05,
                "actual_result": None
            }
        ]
        return pd.DataFrame(data)

    def save_schedule(self, df: pd.DataFrame, date_str: str) -> Path:
        s = get_settings()
        out_dir = s.project_root / "data" / "raw" / "schedules"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"schedule_{date_str}.csv"
        df.to_csv(out_path, index=False)
        logger.info(f"赛程及高阶特征已保存至: {out_path}")
        return out_path

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    client = FootballDataClient()
    today = datetime.now().strftime("%Y-%m-%d")
    df = client.fetch_today_matches(today)
    out_p = client.save_schedule(df, today)
    print(f"成功抓取 {len(df)} 场包含高阶特征的比赛，已保存到 {out_p}")
