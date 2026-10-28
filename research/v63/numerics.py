"""v6.3 offline numerical components. No model calls, no hidden-global posterior.

Only an audited holdings profile may be used to construct experiment references.
Synthetic verification profiles in prepare_numerics.py are explicitly nonexperimental.
"""
from __future__ import annotations

import hashlib
import json
import re
import zipfile
from fractions import Fraction
from decimal import Decimal, localcontext
from pathlib import Path

import cvxpy as cp
import numpy as np
from scipy.optimize import minimize
from sklearn.covariance import LedoitWolf

ROOT = Path(__file__).resolve().parents[2]
INDUSTRIES = ["NoDur", "Durbl", "Manuf", "Enrgy", "Chems", "BusEq", "Telcm", "Utils", "Shops", "Hlth", "Money", "Other"]
SEEDS = dict(development=1001, main=2001, x_replacement=3001, negative_control=4001, execution_order=5001, human_audit=6001, bootstrap=7001)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def jsonable(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {k: jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    return value


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(jsonable(value), ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def displayed_returns(a):
    return np.asarray([float(f"{x:.10f}") for x in np.ravel(a)]).reshape(np.shape(a))


def displayed_covariance(a):
    return np.asarray([float(f"{x:.12g}") for x in np.ravel(a)]).reshape(np.shape(a))


def calibrate(root=ROOT):
    """Read raw percent returns, divide once, compare the existing decimal cache."""
    root = Path(root)
    manifest = json.loads((root / "data/french/manifest.json").read_text(encoding="utf-8-sig"))
    source = manifest["sources"]["ff12_returns"]
    raw_path = root / source["path"]
    if sha256(raw_path) != source["sha256"]:
        raise ValueError("Raw FF12 ZIP hash mismatch")
    with zipfile.ZipFile(raw_path) as archive:
        raw = archive.read(source["members"][0]["name"])
    if hashlib.sha256(raw).hexdigest() != source["members"][0]["sha256"]:
        raise ValueError("Raw FF12 member hash mismatch")
    text = raw.decode("utf-8")
    block = text.split("Average Value Weighted Returns -- Monthly", 1)[1]
    block = block.split("Average Equal Weighted Returns -- Monthly", 1)[0]
    rows = {}
    for line in block.splitlines():
        fields = line.split()
        if len(fields) == 13 and re.fullmatch(r"\d{6}", fields[0]):
            date = fields[0][:4] + "-" + fields[0][4:]
            if "2016-01" <= date <= "2025-12":
                values = np.asarray([float(x) for x in fields[1:]])
                if np.isin(values, [-99.99, -999]).any():
                    raise ValueError("Missing French data in calibration interval")
                rows[date] = values / 100.0
    dates = [f"{y}-{m:02}" for y in range(2016, 2026) for m in range(1, 13)]
    if sorted(rows) != dates:
        raise ValueError("Require exactly 120 complete months 2016-01..2025-12")
    returns = np.array([rows[d] for d in dates])
    cached_path = root / "data/french/monthly_returns.json"
    cached = json.loads(cached_path.read_text(encoding="utf-8-sig"))["datasets"]["FF12"]
    if cached["units"] != "decimal_monthly_return" or cached["columns"] != INDUSTRIES:
        raise ValueError("Unexpected cached units or column order")
    cached_rows = dict(zip(cached["dates"], cached["value_weighted_total_returns"]))
    error = float(np.max(np.abs(returns - np.array([cached_rows[d] for d in dates]))))
    if error > 1e-15:
        raise ValueError(f"Raw/cache disagreement: {error}")
    fit = LedoitWolf(assume_centered=False).fit(returns)
    sigma = displayed_covariance(fit.covariance_)
    prior = displayed_covariance(sigma / 12.0)
    if np.linalg.eigvalsh(sigma).min() <= 0 or np.linalg.eigvalsh(prior).min() <= 0:
        raise ValueError("Roundtripped covariance is not positive definite")
    return dict(industry_codes=INDUSTRIES, dates=dates, observations=120,
                units="decimal monthly total return", raw_to_decimal="percent / 100 exactly once",
                source_url=source["requested_url"], raw_sha256=sha256(raw_path),
                cache_sha256=sha256(cached_path), raw_cache_max_abs_difference=error,
                returns=returns, m0=displayed_returns(returns.mean(axis=0)), Sigma=sigma,
                V0=prior, Omega0=prior.copy(), shrinkage=float(fit.shrinkage_),
                vintage="cached revised French CIZ; not authenticated historical trading replay",
                return_display_decimals=10, covariance_significant_digits=12)


def generate_scenarios(calibration, block="development", count=None):
    """Separate hidden theta ledger from the model-safe signal descriptions."""
    if block not in ("development", "main", "negative_control"):
        raise ValueError("Unknown generation block")
    count = count if count is not None else {"development": 12, "main": 60, "negative_control": 8}[block]
    if count <= 0:
        raise ValueError("Positive count required")
    m0, V0, Omega0 = (np.asarray(calibration[k]) for k in ("m0", "V0", "Omega0"))
    roots = np.random.SeedSequence(SEEDS[block]).spawn(count)
    public, hidden = [], []
    for index, seed in enumerate(roots):
        rng = np.random.Generator(np.random.PCG64(seed))
        r = (0.5, 1.0, 2.0)[index % 3]
        theta = rng.multivariate_normal(m0, V0)
        y = displayed_returns(theta + rng.multivariate_normal(np.zeros(len(m0)), Omega0))
        oi = displayed_covariance(V0 / r)
        x = [displayed_returns(theta + rng.multivariate_normal(np.zeros(len(m0)), oi)) for _ in range(4)]
        if block == "negative_control":
            x = [x[0].copy() for _ in range(4)]
        sid = f"{block}-{index + 1:03d}"
        public.append(dict(scenario_id=sid, r=r, y=y, private_signals={f"F{j+1:02d}": v for j, v in enumerate(x)},
                           Omegai=oi, synthetic_outlook=True,
                           signal_date="2025-09-30" if block == "development" else "2025-12-31",
                           units="decimal monthly return"))
        hidden.append(dict(scenario_id=sid, theta=theta, seed_entropy=SEEDS[block], spawn_key=list(seed.spawn_key)))
    return public, hidden


def replacement_signals(calibration, scenarios, hidden):
    """Balance each 20-case precision stratum, change one epsilon only."""
    if len(scenarios) != 60 or len(hidden) != 60:
        raise ValueError("v6.3 replacement contract requires 60 main scenarios")
    rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence(SEEDS["x_replacement"])))
    targets = {}
    for r in (0.5, 1.0, 2.0):
        strata = [x for x in scenarios if x["r"] == r]
        if len(strata) != 20:
            raise ValueError("Each r stratum must contain 20 scenarios")
        assignment = np.repeat(np.arange(4), 5)
        rng.shuffle(assignment)
        targets.update({s["scenario_id"]: f"F{i+1:02d}" for s, i in zip(strata, assignment)})
    lookup = {x["scenario_id"]: x for x in hidden}
    out = []
    for s in scenarios:
        sid = s["scenario_id"]
        value = displayed_returns(np.asarray(lookup[sid]["theta"]) + rng.multivariate_normal(np.zeros(12), s["Omegai"]))
        out.append(dict(scenario_id=sid, fund_id=targets[sid], replacement_x=value,
                        logical_evidence_ids_unchanged=True, r=s["r"]))
    return out


def posterior(m0, V0, y, Omega0, evidence=()):
    """Posterior ONLY from delivered fragments; correlated fragments merge once.

    evidence items: evidence_id, signal_id, indices, values, precision. Each
    signal_id denotes one private 12-vector with covariance V0 / precision.
    Missing precision is rejected; hidden scenario objects are never accepted.
    """
    m0, V0, y, Omega0 = map(np.asarray, (m0, V0, y, Omega0))
    n = len(m0)
    if y.shape != (n,) or V0.shape != (n, n) or Omega0.shape != (n, n):
        raise ValueError("Posterior input shapes")
    precision = np.linalg.solve(V0, np.eye(n)) + np.linalg.solve(Omega0, np.eye(n))
    information = np.linalg.solve(V0, m0) + np.linalg.solve(Omega0, y)
    groups, seen_ids = {}, set()
    for item in evidence:
        if not {"evidence_id", "signal_id", "indices", "values", "precision"}.issubset(item):
            raise ValueError("Incomplete exposed evidence; precision cannot be inferred")
        if item["evidence_id"] in seen_ids:
            raise ValueError("Duplicate evidence ID")
        seen_ids.add(item["evidence_id"])
        r = float(item["precision"])
        if not np.isfinite(r) or r <= 0:
            raise ValueError("Invalid exposed precision")
        if len(item["indices"]) != len(item["values"]):
            raise ValueError("Observation lengths differ")
        group = groups.setdefault(item["signal_id"], {"r": r, "values": {}})
        if group["r"] != r:
            raise ValueError("Conflicting precision within same private signal")
        for i, value in zip(item["indices"], item["values"]):
            if not isinstance(i, (int, np.integer)) or not 0 <= i < n or not np.isfinite(value):
                raise ValueError("Invalid observation")
            if i in group["values"] and group["values"][i] != float(value):
                raise ValueError("Conflicting duplicate signal coordinate")
            group["values"][i] = float(value)
    for group in groups.values():
        indices = sorted(group["values"])
        H = np.eye(n)[indices]
        values = np.array([group["values"][i] for i in indices])
        # Roundtrip exactly the covariance rule displayed in the source.
        omega = displayed_covariance(V0 / group["r"])
        observed_cov = H @ omega @ H.T
        precision += H.T @ np.linalg.solve(observed_cov, H)
        information += H.T @ np.linalg.solve(observed_cov, values)
    cov = np.linalg.solve(precision, np.eye(n))
    mean = np.linalg.solve(precision, information)
    return dict(mean=mean, covariance=(cov + cov.T) / 2, exposed_evidence_ids=sorted(seen_ids))


def _constraints_arrays(n, A=None, b=None):
    A = np.empty((0, n)) if A is None else np.asarray(A, float).reshape(-1, n)
    b = np.empty(0) if b is None else np.asarray(b, float)
    if b.shape != (len(A),) or not np.isfinite(A).all() or not np.isfinite(b).all():
        raise ValueError("Constraint shape/nonfinite mismatch")
    return A, b


def _active_ellipsoid_polish(mu, h, Sigma, A, b, guess):
    """Independent algebraic solve on candidate active faces, dual-certified.

    The near-optimal objective plane makes generic SOCP interiors extremely
    thin. For each suggested face, solve the affine-section ellipsoid in
    closed form, then verify ALL primal and dual constraints. The approximate
    conic solution only proposes faces; it never certifies a bound.
    """
    n=len(h); cap=float(h@Sigma@h)
    candidates=[]
    for tol in (1e-5,1e-7,1e-9,1e-11):
        support=np.flatnonzero(guess > tol)
        if not len(support):
            continue
        active=np.flatnonzero(np.abs(A@guess-b) < tol * np.maximum(1.0,np.linalg.norm(A,axis=1)))
        # Also consider all inequalities; coordinate-range floors are often
        # inaccurately slack in the preliminary interior-point result.
        for active_idx in (active, np.arange(len(A))):
            B=np.vstack([np.ones(len(support)),A[active_idx][:,support]])
            rhs=np.r_[1.,b[active_idx]]
            S=Sigma[np.ix_(support,support)]
            invB=np.linalg.solve(S,B.T)
            gram=B@invB
            if np.linalg.matrix_rank(gram,tol=1e-13) != len(gram):
                continue
            invgram=np.linalg.inv(gram)
            center=invB@invgram@rhs
            P=np.linalg.inv(S)-invB@invgram@invB.T
            c=mu[support]
            direction=P@c
            spread=float(c@direction)
            remaining=float(cap-center@S@center)
            if spread <= 1e-20 or remaining <= 1e-20:
                continue
            local=center+np.sqrt(remaining/spread)*direction
            w=np.zeros(n); w[support]=local
            if not check_portfolio(w,h,Sigma,A,b,solver=True)["valid"]:
                continue
            lam=.5*np.sqrt(spread/remaining)
            multipliers=np.linalg.lstsq(B.T,c-2*lam*(S@local),rcond=None)[0]
            nu=float(multipliers[0]); a=np.zeros(len(A)); a[active_idx]=multipliers[1:]
            z=2*lam*(Sigma@w)+nu+A.T@a-mu
            z[support]=0
            if (len(a) and a.min() < -1e-8) or z.min() < -1e-8:
                continue
            a=np.maximum(0,a); z=np.maximum(0,z)
            adjusted=mu-A.T@a+z-nu
            bound=float(lam*cap+a@b+nu+adjusted@np.linalg.solve(Sigma,adjusted)/(4*lam))
            primal=float(mu@w)
            if -1e-9 <= bound-primal <= 1e-9:
                candidates.append((bound-primal,w,lam,a,z,nu,bound))
    return min(candidates,key=lambda v:abs(v[0])) if candidates else None


def check_portfolio(raw_weights, h, Sigma, A=None, b=None, *, solver=False):
    """Never normalize, clip, or repair a proposed model portfolio."""
    h, Sigma = np.asarray(h, float), np.asarray(Sigma, float)
    n = len(h)
    A, b = _constraints_arrays(n, A, b)
    try:
        w = np.asarray(raw_weights, float)
    except (ValueError, TypeError):
        return dict(valid=False, failures=["nonnumeric_weights"], raw_weights=raw_weights)
    if w.shape != (n,) or not np.isfinite(w).all():
        return dict(valid=False, failures=["weight_shape_or_nonfinite"], raw_weights=jsonable(w))
    cap = float(h @ Sigma @ h)
    risk = float(w @ Sigma @ w)
    tol = 1e-9 if solver else 1e-6
    risk_tol = 1e-9 if solver else max(1e-10, 1e-6 * cap)
    failures = []
    if abs(w.sum() - 1) > tol:
        failures.append("budget")
    if w.min() < -tol:
        failures.append("lower_bound")
    if risk - cap > risk_tol:
        failures.append("risk_cap")
    residual = A @ w - b
    if len(residual) and residual.max() > tol:
        failures.append("explicit_constraint")
    return dict(valid=not failures, failures=failures, raw_weights=w, budget_residual=float(w.sum()-1),
                minimum_weight=float(w.min()), risk=risk, risk_cap=cap, risk_residual=risk-cap,
                explicit_residuals=residual, budget_lower_tolerance=tol, risk_tolerance=risk_tol)


def normalize_nonnegative_weights(raw_weights):
    """Scale an otherwise usable long-only vector to sum to one.

    The original values are returned alongside the scaled values so the model
    output is never lost. Shape, finiteness, nonnegativity, and a positive sum
    are prerequisites; risk and mandate constraints are deliberately checked
    only after this arithmetic transformation.
    """
    try:
        raw = np.asarray(raw_weights, dtype=float)
    except (TypeError, ValueError):
        return dict(applied=False, reason="nonnumeric_weights", raw_weights=raw_weights)
    if raw.shape != (len(INDUSTRIES),) or not np.isfinite(raw).all():
        return dict(applied=False, reason="weight_shape_or_nonfinite", raw_weights=jsonable(raw))
    if raw.min() < 0:
        return dict(applied=False, reason="negative_weight", raw_weights=jsonable(raw))
    total = float(raw.sum())
    if total <= 0:
        return dict(applied=False, reason="nonpositive_sum", raw_weights=jsonable(raw), raw_sum=total)
    normalized = raw / total
    return dict(applied=True, reason=None, raw_weights=jsonable(raw), raw_sum=total,
                normalized_weights=jsonable(normalized), normalized_sum=float(normalized.sum()))


def _solve_linear(mu, h, Sigma, A=None, b=None, feasible_start=None):
    """Conic solve plus a separate explicit Lagrange upper-bound certificate."""
    mu, h, Sigma = map(lambda x: np.asarray(x, float), (mu, h, Sigma))
    n = len(mu)
    A, b = _constraints_arrays(n, A, b)
    cap = float(h @ Sigma @ h)
    if cap <= 0 or np.linalg.eigvalsh(Sigma).min() <= 0:
        raise ValueError("Positive definite covariance and positive cap required")
    if feasible_start is not None:
        witness=np.asarray(feasible_start,float)
        witness_check=check_portfolio(witness,h,Sigma,A,b,solver=True)
        value=float(mu@witness); simplex_bound=float(np.max(mu))
        if witness_check["valid"] and abs(simplex_bound-value)<=1e-12:
            return dict(weights=witness.copy(),primal_objective=value,dual_bound=max(value,simplex_bound),
                        signed_computed_gap=simplex_bound-value,primal_dual_gap=max(0.,simplex_bound-value),
                        feasibility=witness_check,status="simplex_bound_attained",solver="analytic simplex certificate",
                        certificate="Verified feasible witness attains global simplex linear-objective upper bound")
    w = cp.Variable(n)
    chol = np.linalg.cholesky(Sigma / cap).T
    constraints = [w >= 0, cp.sum(w) == 1, cp.norm(chol @ w, 2) <= 1]
    row_scale = np.maximum(np.max(np.abs(A), axis=1), np.abs(b)) if len(A) else np.empty(0)
    row_scale = np.maximum(row_scale, 1e-12)
    if len(A):
        constraints.append((A / row_scale[:, None]) @ w <= b / row_scale)
    problem = cp.Problem(cp.Maximize(mu @ w), constraints)
    solver_error=None
    try:
        problem.solve(solver="CLARABEL", max_iter=500, tol_gap_abs=1e-11,
                      tol_gap_rel=1e-11, tol_feas=1e-11)
    except cp.error.SolverError as exc:
        solver_error=str(exc)
    if w.value is None:
        second=independent_solve(mu,h,Sigma,A,b)
        guess=np.asarray(second["weights"])
    else:
        guess=np.asarray(w.value).ravel()
    polished=_active_ellipsoid_polish(mu,h,Sigma,A,b,guess)
    if polished is None and feasible_start is not None:
        polished=_active_ellipsoid_polish(mu,h,Sigma,A,b,np.asarray(feasible_start))
    if polished is None and feasible_start is not None:
        alternate=np.asarray(feasible_start).copy()
        alternate[np.argmax(mu)]=max(alternate[np.argmax(mu)],1e-3)
        polished=_active_ellipsoid_polish(mu,h,Sigma,A,b,alternate)
    if polished is not None:
        gap,weights,lam,a,z,nu,dual_bound=polished
        primal=float(mu@weights)
        return dict(weights=weights,primal_objective=primal,dual_bound=max(primal,dual_bound),
                    signed_computed_gap=gap,primal_dual_gap=max(0.,gap),
                    feasibility=check_portfolio(weights,h,Sigma,A,b,solver=True),
                    status="analytic_active_face_dual_certified", solver="CLARABEL + analytic active ellipsoid",
                    preliminary_conic_status=problem.status, preliminary_conic_error=solver_error,
                    dual_risk=lam,dual_explicit=a,dual_lower=z,dual_budget=nu,
                    certificate="Closed-form affine ellipsoid solution; independent full primal/dual residual and Lagrange upper bound")
    if problem.status not in (cp.OPTIMAL, cp.OPTIMAL_INACCURATE) or w.value is None:
        raise RuntimeError(f"Reference solver failure: {problem.status}; {solver_error}")
    weights=guess
    check = check_portfolio(weights, h, Sigma, A, b, solver=True)
    if not check["valid"]:
        raise RuntimeError(f"Reference primal residual failure: {check}")
    z = np.maximum(0, np.asarray(constraints[0].dual_value).ravel())
    nu = float(constraints[1].dual_value)
    lam = max(0.0, float(np.asarray(constraints[2].dual_value).item()) / (2*cap))
    a = np.maximum(0, np.asarray(constraints[3].dual_value).ravel()) / row_scale if len(A) else np.empty(0)
    adjusted = mu - A.T @ a
    # Retaining the simplex gives a valid upper bound even when risk is inactive.
    linear_bound = float(np.max(adjusted) + a @ b)
    c = adjusted + z - nu
    quadratic_bound = float(lam * cap + a @ b + nu + c @ np.linalg.solve(Sigma, c)/(4*lam)) if lam > 0 else float("inf")
    dual_bound = min(linear_bound, quadratic_bound)
    primal = float(mu @ weights)
    gap = dual_bound - primal
    # Tiny negative gaps are disclosed, never treated as positive evidence.
    if gap < -1e-9 or gap > 1e-9:
        raise RuntimeError(f"Reference primal-dual gap {gap} exceeds 1e-9")
    return dict(weights=weights, primal_objective=primal, dual_bound=max(primal, dual_bound),
                signed_computed_gap=gap, primal_dual_gap=max(0.0, gap),
                feasibility=check, status=problem.status, solver="CLARABEL",
                dual_risk=lam, dual_explicit=a, dual_lower=z, dual_budget=nu,
                certificate="Lagrangian quadratic bound and simplex linear bound; finite feasibility tolerance 1e-9")


def independent_solve(mu, h, Sigma, A=None, b=None):
    """Independent SLSQP implementation, starting only at h, no conic result."""
    mu, h, Sigma = map(lambda x: np.asarray(x, float), (mu, h, Sigma))
    A, b = _constraints_arrays(len(mu), A, b)
    cap = float(h @ Sigma @ h)
    cons = [dict(type="eq", fun=lambda w: w.sum()-1, jac=lambda w: np.ones(len(w))),
            dict(type="ineq", fun=lambda w: 1 - w @ Sigma @ w / cap,
                 jac=lambda w: -2 * Sigma @ w / cap)]
    if len(A):
        cons.append(dict(type="ineq", fun=lambda w: b-A@w, jac=lambda w: -A))
    fit = minimize(lambda w: -mu@w, h.copy(), jac=lambda w: -mu,
                   method="SLSQP", bounds=[(0, 1)]*len(h), constraints=cons,
                   options=dict(ftol=1e-13, maxiter=2000))
    check = check_portfolio(fit.x, h, Sigma, A, b, solver=True)
    return dict(weights=fit.x, objective=float(mu@fit.x), success=bool(fit.success),
                message=str(fit.message), feasibility=check, iterations=int(fit.nit))


def _exact_minimum_variance_boundary(mu,h,Sigma,A=None,b=None):
    """Certify a zero-radius risk set with exact binary-rational arithmetic.

    For sum(w)=1, w'Sw = rho + (w-v)'S(w-v), where
    v=S^-1 1/(1'S^-1 1) and rho=1/(1'S^-1 1).  Positive definite
    S and cap=rho imply the singleton v; no finite conic multiplier is needed.
    No risk cap is enlarged. Nonzero-radius cases return to the general solver.
    """
    n=len(h); S=[[Fraction.from_float(float(x)) for x in row] for row in Sigma]
    hf=[Fraction.from_float(float(x)) for x in h]
    mf=[Fraction.from_float(float(x)) for x in mu]
    aug=[row.copy()+[Fraction(1)] for row in S]
    for k in range(n):
        pivot=next((i for i in range(k,n) if aug[i][k]),None)
        if pivot is None: raise ValueError("Singular exact covariance")
        aug[k],aug[pivot]=aug[pivot],aug[k]
        scale=aug[k][k]; aug[k]=[x/scale for x in aug[k]]
        for i in range(n):
            if i!=k:
                scale=aug[i][k]
                aug[i]=[x-scale*y for x,y in zip(aug[i],aug[k])]
    inverse_one=[row[-1] for row in aug]
    denominator=sum(inverse_one)
    vf=[x/denominator for x in inverse_one]
    rho=1/denominator
    cap=sum(hf[i]*S[i][j]*hf[j] for i in range(n) for j in range(n))
    if cap!=rho:
        return None
    weights=np.array([float(v) for v in vf])
    A,b=_constraints_arrays(n,A,b)
    # Exact source constraints; floats are merely encodings of their values.
    if any(v<0 for v in vf): return None
    for row,bound in zip(A,b):
        if sum(Fraction.from_float(float(a))*v for a,v in zip(row,vf))>Fraction.from_float(float(bound)):
            return None
    value=sum(m*v for m,v in zip(mf,vf)); primal=float(value)
    lower=np.nextafter(weights,-np.inf); upper=np.nextafter(weights,np.inf)
    lower=np.maximum(0,lower);upper=np.minimum(1,upper)
    check=check_portfolio(weights,h,Sigma,A,b,solver=True)
    if not check["valid"]: raise RuntimeError("Exact boundary failed float residual checks")
    return dict(weights=weights,primal_objective=primal,
                dual_bound=float(np.nextafter(primal,np.inf)),
                signed_computed_gap=float(np.nextafter(primal,np.inf)-primal),
                primal_dual_gap=float(np.nextafter(primal,np.inf)-primal),
                feasibility=check,status="exact_singleton_risk_set_certified",
                solver="exact Fraction Gaussian elimination and positive-definite quadratic identity",
                certificate="Exact rational cap=rho and sum(v)=1; SPD quadratic identity forces w=v",
                exact_budget_residual=str(sum(vf)-1),exact_risk_radius=str(cap-rho),
                coordinate_lower=lower,coordinate_upper=upper,near_optimal_epsilon=1e-9,
                coordinate_dual_gap_max=0.0,coordinate_bound_padding="one outward float ULP",
                eta=float(.5*np.maximum(weights-lower,upper-weights).sum()),
                one_percentage_point_width_diagnostic=False,
                independent_crosscheck={"method":"exact rational quadratic identity; no numerical dual multiplier assumed", "success":True},
                independent_objective_abs_difference=0.0)


def solve_reference(mu, h, Sigma, A=None, b=None, *, coordinate_ranges=True, crosscheck=True):
    h = np.asarray(h, float)
    if not check_portfolio(h, h, Sigma, A, b, solver=True)["valid"]:
        raise ValueError("Starting holdings infeasible; never enlarge risk cap or repair h")
    gradient=np.asarray(Sigma)@h
    if np.ptp(gradient) <= 1e-13 and np.min(h) >= 0:
        boundary=_exact_minimum_variance_boundary(np.asarray(mu,float),h,np.asarray(Sigma,float),A,b)
        if boundary is not None: return boundary
        raise RuntimeError("near_minimum_variance_boundary: exact singleton certificate does not apply; risk cap is never expanded")
    result = _solve_linear(mu, h, Sigma, A, b)
    if crosscheck:
        second = independent_solve(mu, h, Sigma, A, b)
        difference = abs(second["objective"]-result["primal_objective"])
        if not second["success"] or not second["feasibility"]["valid"] or difference > 1e-9:
            raise RuntimeError(f"Independent solver disagreement: {difference}; {second['message']}")
        result["independent_crosscheck"] = second
        result["independent_objective_abs_difference"] = difference
    if coordinate_ranges:
        n = len(h)
        A0, b0 = _constraints_arrays(n, A, b)
        eps = 1e-9
        An = np.vstack((A0, -np.asarray(mu)))
        bn = np.r_[b0, -(result["primal_objective"]-eps)]
        lower, upper, gaps = [], [], []
        for k in range(n):
            axis = np.eye(n)[k]
            try:
                lo = _solve_linear(-axis,h,Sigma,An,bn,feasible_start=result["weights"])
                hi = _solve_linear(axis,h,Sigma,An,bn,feasible_start=result["weights"])
            except Exception as exc:
                raise RuntimeError(f"Coordinate {k} reference range failed: {exc}") from exc
            # Dual bounds are outer ranges, not the inner primal estimates.
            lower.append(max(0.0, -lo["dual_bound"]-1e-9))
            upper.append(min(1.0, hi["dual_bound"]+1e-9))
            gaps += [lo["primal_dual_gap"], hi["primal_dual_gap"]]
        lower, upper = np.array(lower), np.array(upper)
        v = result["weights"]
        result.update(coordinate_lower=lower, coordinate_upper=upper, near_optimal_epsilon=eps,
                      coordinate_dual_gap_max=max(gaps), coordinate_bound_padding=1e-9,
                      eta=float(.5*np.maximum(v-lower, upper-v).sum()),
                      one_percentage_point_width_diagnostic=bool(np.any(upper-lower > .01)))
    return result


def tv(a, b):
    return float(.5*np.abs(np.asarray(a)-np.asarray(b)).sum())


def pair_metrics(wi, wj, ref_i, ref_j):
    vi, vj = np.asarray(ref_i["weights"]), np.asarray(ref_j["weights"])
    d, ds = tv(wi, wj), tv(vi, vj)
    eta = ref_i["eta"] + ref_j["eta"]
    e = tv(np.asarray(wi)-np.asarray(wj), vi-vj)
    dslo, dshi = max(0.0, ds-eta), min(1.0, ds+eta)
    glo, ghi = dslo-d, dshi-d
    return dict(D=d, Dstar=ds, G=ds-d, E=e, A=abs(ds-d),
                Dstar_interval=[dslo, dshi], G_interval=[glo, ghi],
                E_interval=[max(0.0, e-eta), e+eta],
                A_interval=[0.0 if glo <= 0 <= ghi else min(abs(glo),abs(ghi)), max(abs(glo),abs(ghi))])


def regret_bounds(mu, w, reference):
    achieved = float(np.asarray(mu) @ np.asarray(w))
    return [reference["primal_objective"]-achieved-1e-9, reference["dual_bound"]-achieved+1e-9]


def policy_weights(raw, h, Sigma, A=None, b=None, *, terminal_status):
    if terminal_status in ("not_attempted", "protocol_violation"):
        raise ValueError("Unattempted/protocol-invalid slots cannot be filled with h")
    check = check_portfolio(raw, h, Sigma, A, b)
    if terminal_status == "valid_final" and check["valid"]:
        return dict(weights=np.asarray(raw), fallback=False, validation=check)
    if terminal_status in ("model_output_failure", "operational_failure"):
        return dict(weights=np.asarray(h).copy(), fallback=True, validation=check)
    raise ValueError("Inconsistent terminal status or invalid raw portfolio")
