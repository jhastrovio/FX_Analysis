
# 📘 Return Metrics: Python Code Summary

---

## 1. Geometric Annualized Return

### ✅ Definition
The geometric annualized return reflects the compound rate of return per year, accounting for daily reinvestment.

### 🔢 Formula
Let:

- `r_t` = daily return (decimal)
- `N` = number of trading days
- `A` = annualization factor (260)

\[
R_{	ext{geom}} = \left( \prod_{t=1}^{N} (1 + r_t) 
ight)^{rac{A}{N}} - 1
\]

### 🐍 Python
```python
def annualized_return(returns, annualization_factor=252):
    cumulative_return = (1 + returns).prod()
    n_days = len(returns)
    return cumulative_return**(annualization_factor / n_days) - 1
```

---

## 2. Annualized Volatility

### ✅ Definition
Standard deviation of daily returns, scaled to an annual level.

### 🔢 Formula
\[
\sigma_{	ext{annual}} = \sigma_{	ext{daily}} 	imes \sqrt{A}
\]

### 🐍 Python
```python
import numpy as np

def annualized_volatility(returns, annualization_factor=260):
    return returns.std() * np.sqrt(annualization_factor)
```

---

## 3. Sharpe Ratio (Based on Calendar Monthly Returns)

### ✅ Definition
Sharpe ratio based on returns between calendar month-end values (not annualized).

### 🔢 Formula
\[
	ext{Sharpe}_{	ext{monthly}} = rac{ar{r}_{	ext{monthly}}}{\sigma_{	ext{monthly}}}
\]

### 🐍 Python
```python
def monthly_sharpe_from_cumulative(cumulative_index):
    monthly_index = cumulative_index.resample("M").last()
    monthly_returns = monthly_index.pct_change().dropna()
    return monthly_returns.mean() / monthly_returns.std()
```

---

## 4. Rolling Window Metrics

### 🔢 Purpose
Use rolling windows to analyze time-varying performance metrics (e.g., rolling Sharpe or volatility).

### 🐍 Python Examples
```python
# Rolling annualized volatility over 3 months (63 trading days)
rolling_vol = daily_returns.rolling(window=63).std() * np.sqrt(260)

# Rolling geometric return (approximated using average return)
rolling_geom_return = ((1 + daily_returns).rolling(63).apply(np.prod, raw=True))**(260/63) - 1

# Rolling Sharpe ratio (daily basis)
rolling_sharpe = daily_returns.rolling(63).mean() / daily_returns.rolling(63).std()
```

---

Let me know if you want to add risk-adjusted metrics like Sortino ratio, max drawdown, or plotting tools.
