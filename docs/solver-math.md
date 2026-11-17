# Constraint Solving & Mobility Math

LinkLab combines **first-order tangent spaces**, **second-order prestress stability (Hessian obstruction)**, **unilateral cable cone conditions**, and **nonlinear manifold projection** across both the Python solver (`kinematics/src/kinematics/core/`) and the JavaScript Web Worker solver (`src/solver/engine.ts`).

---

## 1. Quadratic Constraint System

In `numerical_model.py`, every equality constraint is normalized by the scene scale $s$ into a quadratic polynomial:

$$f_r(x) = \frac{1}{2} x^\top Q_r x + b_r^\top x + c_r = 0$$

- **Bars / distance constraints:**
  $$\frac{\|x_i - x_j\|^2 - \ell^2}{2s^2} = 0$$
- **Pins, coincidences, planes, affine body attachments:** linear equations ($Q_r = 0$).
- **Parallels:** cross-product components $(x_j - x_i) \times (x_l - x_k) = 0$ (bilinear quadratic, $3$ equations in 3D, $1$ in 2D).
- **Ideal cables (inequalities):**
  $$g_c(x) = \frac{\|x_i - x_j\|^2 - \ell_c^2}{2s^2} \le 0$$

---

## 2. First-Order Tangent Space & Self-Stresses

At configuration $x \in \mathbb{R}^n$, the equality Jacobian $J(x) = \nabla f(x) \in \mathbb{R}^{m \times n}$ is decomposed via SVD (`null_space` / `nullspaces`):

- **Infinitesimal flexes (1st-order tangents):** $T = \ker J(x) \in \mathbb{R}^{n \times k}$, where $J(x)\dot{x} = 0$ for $\dot{x} = T v$.
- **Self-stresses (equilibrium stresses):** $U = \ker J(x)^\top$, vectors $u$ satisfying $J(x)^\top u = 0$.

---

## 3. Second-Order Obstruction (Prestress Stability)

Differentiating $f(x(t)) = 0$ twice along a smooth curve $x(t) = x + t\dot{x} + \frac{1}{2}t^2\ddot{x} + \dots$ yields:

$$J(x)\ddot{x} + \left(\dot{x}^\top \nabla^2 f_r(x)\, \dot{x}\right)_r = 0$$

Multiplying on the left by any self-stress $u \in \ker J(x)^\top$ eliminates $u^\top J(x)\ddot{x} = 0$, leaving the **stress-stiffness quadratic form** restricted to $T$:

$$v^\top H_u v = 0, \qquad H_u = T^\top \left(\sum_r u_r Q_r\right) T \in \mathbb{R}^{k \times k}$$

Eigenvalues of each $H_u$ are checked (`eigvalsh` / `eigenvalues`, tolerance $10^{-8}$):

- **Semidefinite $H_u$** ($\lambda_{\min} \ge -10^{-8}, \lambda_{\max} > 10^{-8}$, or vice versa): the only solutions to $v^\top H_u v = 0$ lie in $\ker H_u$. These kernels are intersected with $T$ to form `linear_compatible_tangents`.
- **Locked (`"locked"`):** `linear_compatible_dimension == 0` while $k > 0$ — the mechanism has infinitesimal mobility but is second-order rigid.
- **Inconclusive (`"inconclusive"`):** nonzero indefinite $H_u$ remain, forming a quadratic cone rather than a linear subspace. During **Wander** (`exploration.py`), LinkLab probes escape directions by solving the quadratic cone system $v^\top H_u v = 0,\ \|v\| = 1$ with nonlinear least squares.
- **Compatible (`"compatible"`):** all quadratic forms vanish on $T$.

---

## 4. Unilateral Cables (`cable_mobility` / `cableMobility`)

Let $\mathcal{A}$ be the set of active (taut) cables where $(\ell_c - \|x_i - x_j\|)/s \le 10^{-8}$, with gradient matrix $A_{\mathcal{A}} = \nabla g_{\mathcal{A}}(x)$.

1. **Non-negative equilibrium stress search:** We look for cable tensions $\mu \ge 0$ ($\mathbf{1}^\top \mu = 1$) balanced by equality constraint reactions $\lambda$:
   $$J(x)^\top \lambda + A_{\mathcal{A}}^\top \mu = 0$$
   Projecting onto $T = \ker J(x)$ eliminates $\lambda$ via $(A_{\mathcal{A}} T)^\top \mu = 0$, solved using the rank-aware active-set QP solver (`constrained_fit` / `constrainedFit`).
2. **Forced active cables:** Any cable with $\mu_c > 10^{-8}$ cannot slacken along a feasible 2nd-order motion, so $A_{\text{forced}} \dot{x} = 0$ is intersected into the tangent basis.
3. **Combined 2nd-order Hessian:** Using both $\lambda$ and $\mu$, the combined stress-stiffness matrix
   $$H = T_{\text{res}}^\top \left(\sum_r \lambda_r Q_r + \sum_{c \in \mathcal{A}} \mu_c \nabla^2 g_c\right) T_{\text{res}}$$
   is checked for semidefiniteness to prune any remaining locked directions (`motion_kind: "cone" | "locked"`).

---

## 5. Dragging, Nonlinear Projection & Ghost Preview

- **Equality-only `project(guess)`:** Damped **Levenberg–Marquardt** solving $(J^\top J + \lambda I)\delta = -J^\top r$ until $\|r\|_\infty \le 10^{-10}$.
- **Cable `project(guess)`:** Sequential equality + inequality projection: computes an equality Newton step $p$ via $J$, then projects $-p$ into $\ker J$ subject to linearized cable upper bounds $A (p + Z q) \le -g(x)$ via active-set `constrainedFit`.
- **Interactive `drag` (up to 16 iterations):** Computes a least-squares (or cable-constrained QP) step inside the current `mobility().basis` toward the cursor target, caps step length at $0.03s$, and backtracks (`1, 0.5, 0.25, 0.125`) through `project()`—accepting only steps that stay on the manifold and strictly reduce cursor error.
- **Ghost preview (`preview()`, 20 Hz):** When a drag target is unreachable, a separate Web Worker solves a regularized soft-penalty fit pinned to the cursor to highlight which rods or constraints would stretch or break.

---

## Key Source Files

- `kinematics/src/kinematics/core/numerical_model.py` — quadratic model export
- `kinematics/src/kinematics/core/engine.py` — Python mobility, projection, and drag
- `kinematics/src/kinematics/core/inequalities.py` — active-set QP & cable mobility
- `kinematics/src/kinematics/core/exploration.py` — quadratic cone probing for Wander
- `src/solver/engine.ts` — JavaScript Web Worker solver & ghost preview
- `src/solver/client.ts` — backend dispatch & 20 Hz ghost worker scheduling
