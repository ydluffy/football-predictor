from __future__ import annotations

import pandas as pd
import numpy as np

def calculate_ev_and_kelly(
    predictions: pd.DataFrame, 
    odds_home: pd.Series, 
    odds_draw: pd.Series, 
    odds_away: pd.Series,
    bankroll_fraction: float = 1.0,
    kelly_fraction: float = 0.25 # Kelly multiplier (e.g. fractional Kelly)
) -> pd.DataFrame:
    """
    计算每场比赛的主胜、平局、客胜的期望价值 (EV) 和凯利建议仓位 (Kelly Fraction)。
    
    predictions: 包含 p_home, p_draw, p_away 的 DataFrame
    odds_*: 真实的赔率数据
    bankroll_fraction: 可用资金的比例
    kelly_fraction: 凯利乘数（通常建议使用 0.25 或 0.5 降低风险）
    """
    out = predictions.copy()
    
    eps = 1e-6
    oh = odds_home.fillna(1.0).clip(lower=1.0 + eps)
    od = odds_draw.fillna(1.0).clip(lower=1.0 + eps)
    oa = odds_away.fillna(1.0).clip(lower=1.0 + eps)

    # EV = P * Odds - 1
    out['ev_home'] = (out['p_home'] * oh) - 1.0
    out['ev_draw'] = (out['p_draw'] * od) - 1.0
    out['ev_away'] = (out['p_away'] * oa) - 1.0
    
    # Kelly = (P * Odds - 1) / (Odds - 1)
    out['kelly_home'] = ((out['p_home'] * oh - 1.0) / (oh - 1.0)).clip(lower=0) * kelly_fraction
    out['kelly_draw'] = ((out['p_draw'] * od - 1.0) / (od - 1.0)).clip(lower=0) * kelly_fraction
    out['kelly_away'] = ((out['p_away'] * oa - 1.0) / (oa - 1.0)).clip(lower=0) * kelly_fraction
    
    # Generate betting recommendation
    def recommend(row):
        evs = {'H': row['ev_home'], 'D': row['ev_draw'], 'A': row['ev_away']}
        kellys = {'H': row['kelly_home'], 'D': row['kelly_draw'], 'A': row['kelly_away']}
        
        best_choice = max(evs.items(), key=lambda x: x[1])
        choice, ev = best_choice
        
        if ev > 0.05: # EV threshold
            return f"推荐投注: {choice}, EV: {ev:.3f}, 建议仓位: {kellys[choice]*100:.1f}%"
        return "无推荐投注 (EV不足)"

    out['betting_recommendation'] = out.apply(recommend, axis=1)
    return out
