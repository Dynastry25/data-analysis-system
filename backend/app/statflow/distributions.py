"""Probability distribution helpers for the statistical engine (no scipy needed).

Implements the regularized incomplete beta / gamma functions, the Student t,
chi-square and F survival functions, a Student t quantile (for confidence
intervals) and the Fisher z interval for correlations.

Accuracy is more than enough for reporting p-values and confidence intervals; the
implementations are checked in ``tests/statflow_test.py``.
"""

import math

FPMIN = 1e-300
MAX_ITER = 300
EPS = 3e-16


# --------------------------------------------------------------- incomplete beta


def _betacf(a: float, b: float, x: float, max_iter: int = MAX_ITER) -> float:
    """Continued fraction for the incomplete beta function (Lentz's method)."""
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < FPMIN:
        d = FPMIN
    d = 1.0 / d
    h = d
    for m in range(1, max_iter + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        h *= d * c

        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < EPS:
            break
    return h


def betai(a: float, b: float, x: float) -> float:
    """Regularized incomplete beta function I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    bt = math.exp(
        math.lgamma(a + b)
        - math.lgamma(a)
        - math.lgamma(b)
        + a * math.log(x)
        + b * math.log(1.0 - x)
    )
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


# ------------------------------------------------------------ incomplete gamma


def _gser(a: float, x: float) -> float:
    """Series representation of P(a, x) (lower regularized incomplete gamma)."""
    ap = a
    total = 1.0 / a
    delta = total
    for _ in range(MAX_ITER):
        ap += 1.0
        delta *= x / ap
        total += delta
        if abs(delta) < abs(total) * EPS:
            break
    return total * math.exp(-x + a * math.log(x) - math.lgamma(a))


def _gcf(a: float, x: float) -> float:
    """Continued fraction representation of Q(a, x) (upper regularized)."""
    b = x + 1.0 - a
    c = 1.0 / FPMIN
    d = 1.0 / b
    h = d
    for i in range(1, MAX_ITER + 1):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < FPMIN:
            d = FPMIN
        c = b + an / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < EPS:
            break
    return math.exp(-x + a * math.log(x) - math.lgamma(a)) * h


def gammap(a: float, x: float) -> float:
    """Regularized lower incomplete gamma P(a, x)."""
    if x <= 0.0:
        return 0.0
    if x < a + 1.0:
        return _gser(a, x)
    return 1.0 - _gcf(a, x)


def gammaq(a: float, x: float) -> float:
    """Regularized upper incomplete gamma Q(a, x) = 1 - P(a, x)."""
    if x <= 0.0:
        return 1.0
    if x < a + 1.0:
        return 1.0 - _gser(a, x)
    return _gcf(a, x)


def normal_cdf(z: float) -> float:
    """Standard normal CDF."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def normal_sf(z: float) -> float:
    """Standard normal upper tail."""
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def normal_ppf(p: float) -> float:
    """Standard normal quantile (bisection: fast enough and always stable)."""
    if p <= 0.0:
        return float("-inf")
    if p >= 1.0:
        return float("inf")
    low, high = -40.0, 40.0
    for _ in range(200):
        mid = (low + high) / 2.0
        if normal_cdf(mid) < p:
            low = mid
        else:
            high = mid
    return (low + high) / 2.0


def student_t_sf(t: float, dof: float) -> float:
    """P(T > t) for a Student t distribution with ``dof`` degrees of freedom."""
    if dof <= 0:
        return 1.0
    x = dof / (dof + t * t)
    two_sided = betai(dof / 2.0, 0.5, x)
    return two_sided / 2.0 if t > 0 else 1.0 - two_sided / 2.0


def student_t_cdf(t: float, dof: float) -> float:
    return 1.0 - student_t_sf(t, dof)


def student_t_two_sided_p(t: float, dof: float) -> float:
    """Two-sided p-value P(|T| > |t|)."""
    return min(max(2.0 * student_t_sf(abs(t), dof), 0.0), 1.0)


def student_t_ppf(p: float, dof: float) -> float:
    """Student t quantile via bisection on the CDF."""
    if dof <= 0:
        return float("nan")
    if p <= 0.0:
        return float("-inf")
    if p >= 1.0:
        return float("inf")
    low, high = -200.0, 200.0
    for _ in range(200):
        mid = (low + high) / 2.0
        if student_t_cdf(mid, dof) < p:
            low = mid
        else:
            high = mid
    return (low + high) / 2.0


def t_critical(dof: float, level: float = 0.95) -> float:
    """Two-sided critical value used for confidence intervals."""
    return student_t_ppf(1.0 - (1.0 - level) / 2.0, dof)


def chi_square_sf(x: float, dof: float) -> float:
    """Upper tail P(X > x) for a chi-square distribution."""
    if dof <= 0 or x <= 0:
        return 1.0
    return gammaq(dof / 2.0, x / 2.0)


def chi_square_cdf(x: float, dof: float) -> float:
    return 1.0 - chi_square_sf(x, dof)


def f_sf(f_value: float, df1: float, df2: float) -> float:
    """Upper tail of the F distribution."""
    if f_value <= 0 or df1 <= 0 or df2 <= 0:
        return 1.0
    return betai(df2 / 2.0, df1 / 2.0, df2 / (df2 + df1 * f_value))


def fisher_z_interval(
    r: float, n: int, level: float = 0.95
) -> tuple[float, float] | None:
    """Confidence interval for a correlation coefficient (Fisher z transform)."""
    if n <= 3 or abs(r) >= 1.0:
        return None
    z = math.atanh(r)
    standard_error = 1.0 / math.sqrt(n - 3)
    z_critical = normal_ppf(1.0 - (1.0 - level) / 2.0)
    return (
        math.tanh(z - z_critical * standard_error),
        math.tanh(z + z_critical * standard_error),
    )

