"""
THIS FILE CONTAINS THE METHODS FOR THE INTERIOR POINT ALGORITHM EXECUTION for the PORTFOLIO OPTIMIZATION.
"""
import numpy as np

class IntPoint:
    """This class contains an implementation of a modified version of the Mehrotra predictor-corrector method for linear programming.
    Thanks to some modifications the method is now suited for convex quadratic programming problems.
    """

    def __init__(self
                , S: np.array
                , A: np.array
                , b: np.array
                , c: np.array
                , const=0.0
                , max_iteration=1000
                , epsilon = 1.0e-5
                , max=True
                , verbose=False) -> None:
        """
        Initializes an Interior Point session in the standard form for solving a quadratic program
            min x^T S x + x^T c + const s.t. A @ x >= b
        where:
            - S is a symmetric positive semi-definite matrix
            - A is the matrix of coefficients for the constraint equations
            - b is the vector of constants on the RHS of the constraint equations
        This code follows the algorithm presented in Nocedal & Wright (2006)[Numerical Optimization], the 
        "Predictor-Corrector Algorithm for QP"
        """
        self.S = S
        self.A = A
        self.b = b.reshape((1, b.shape[0]))
        self.c = c
        self.const = const

        self.n_vars = self.A.shape[1]
        self.n_eq   = self.A.shape[0]

        self.iteration      = 0
        self.verbose        = verbose
        self.max_iteration  = max_iteration
        self.epsilon        = epsilon          # for the tolerance

        # Initialization variables: user-defined starting point
        # TODO generate it randomically and check if respect the constraints
        self.x_0  = np.ones(self.n_vars)
        # Slack and Lambdas must be positive
        self.y_0  = 0.3 * np.ones(self.n_eq)        # slack
        self.lm_0 = 0.6 * np.ones(self.n_eq)        # langrangian multiplier

    def compute_mu(self, y_k, lm_k):
        return (y_k.T @ lm_k) / self.n_eq

    def corrector_step(self, x_k, y_k, lm_k, Gamma_aff, Lambda_aff, sigma):
        """It computes the affine scaling step (w_aff, y_aff, lm_aff) from the point (x_k, y_k, lm_k)
        by solving the system built with the perturbed KKT conditions for the given convex quadratic program.

        The linear system is of the form:
        [G  0 -A.T [d_x   [      -rd
         A -I  0    d_y  =       -rp
         0  LA GA ] d_lm]  -LA @ GA @ e + sigma @ mu @ e]
        Obtained by fixing mu and applying the Newton's method to KKT conditions.
        """
        # Linear system computation
        Gamma = np.diag(y_k)
        Lambda = np.diag(lm_k)
        rd = self.S @ x_k - self.A.T @ lm_k + self.c.T
        rp = self.A @ x_k - y_k - self.b
        mu = self.compute_mu(y_k, lm_k)         # the complementarity measure
        e = np.zeros((self.n_eq))

        # Left hand side of the linear system
        LHS = np.block([
            [self.S, np.zeros((self.n_vars, self.n_eq)), -self.A.T],
            [self.A, -np.eye(self.n_eq), np.zeros((self.n_eq, self.n_eq))],
            [np.zeros((self.n_eq, self.n_vars)), Lambda, Gamma]
        ])

        # Right hand side of the linear system
        RHS = np.block([
            -rd,
            -rp,
            -Lambda @ Gamma @ e - Lambda_aff @ Gamma_aff @ e + sigma * mu * e
        ])

        # Solve the linear system to obtain the step's coordinates
        solutions = np.linalg.solve(LHS, RHS.T)
        # The first n_vars values are the xs
        dx = solutions[:self.n_vars]
        # The first n_vars * n_eq values are the slack variables
        dy = solutions[self.n_vars:self.n_vars + self.n_eq]
        # The remaining ones are the lambdas
        dlm = solutions[-self.n_eq:]

        return dx.reshape((dx.shape[0],)), dy.reshape((dy.shape[0],)), dlm.reshape((dlm.shape[0],))

    def compute_affine_step_size(self, y_k, lm_k, dy_aff, dlm_aff):
        """It computes the stepsize accordingly to:
        (y_k, lm_k) + step * (y_aff, lm_aff) >= 0
        while 0 < step <= 1.
        """
        step = 1.0
        arr_k = np.concatenate([y_k, lm_k])
        arr_aff = np.concatenate([dy_aff, dlm_aff])
        while any((arr_k + step * arr_aff) < np.zeros(2*self.n_eq)) and step > 0:
            step -= 0.05

        return step

    def compute_primal_dual_step_size(self, y_k, lm_k, dy, dlm):
        """It computes the stepsize by choosing the minimum between the primal step size
        and the dual one.
        """
        # To accelerate convergence tau will approach 1
        tau = 1 - 0.5**(self.iteration + 1)

        step_primal = 1.0
        while y_k + step_primal * dy < (1 - tau) * y_k and step_primal > 0:
            step_primal -= 0.05

        step_dual = 1.0
        while lm_k + step_dual * dlm < (1 - tau) * lm_k and step_dual > 0:
            step_dual -= 0.05
        return np.min([step_primal, step_dual])

    def solve(self):
        """Predictor
        """

        # Initialization step
        Gamma_aff = np.zeros((self.n_eq, self.n_eq))
        Lambda_aff = np.zeros((self.n_eq, self.n_eq))

        # The first step computes an affine scaling step by setting sigma to zero
        _, dy_aff, dlm_aff = self.corrector_step(self.x_0, self.y_0, self.lm_0, Gamma_aff, Lambda_aff, sigma=0)

        # Apply the step to the starting point
        x_k = self.x_0
        y_k = np.maximum(1, np.absolute(dy_aff + self.y_0))            # max and absolute values must be applied component-wise
        lm_k = np.maximum(1, np.absolute(dlm_aff + self.lm_0))

        while self.iteration < self.max_iteration:

            # Perform an affine step
            dx_aff, dy_aff, dlm_aff = self.corrector_step(x_k, y_k, lm_k, Gamma_aff, Lambda_aff, sigma=0)
            mu = self.compute_mu(y_k, lm_k)

            step_aff = self.compute_affine_step_size(y_k, lm_k, dy_aff, dlm_aff)
            mu_aff = ((y_k * step_aff * dy_aff).T @ (lm_k * step_aff * dlm_aff)) / self.n_eq

            # Set the centering parameter
            sigma = (mu_aff / mu)**3

            # ?
            Gamma_aff = np.diag(dy_aff)
            Lambda_aff = np.diag(dlm_aff)

            dx, dy, dlm = self.corrector_step(x_k, y_k, lm_k, Gamma_aff, Lambda_aff, sigma)

            step = self.compute_primal_dual_step_size(y_k, lm_k, dy, dlm)

            # Update step
            x_k += step * dx
            y_k += step * dy
            lm_k += step * dlm

            var = np.concatenate([dx, dy, dlm])
            if np.linalg.norm(var) < self.epsilon:
                raise Exception(f'PRECISION REACHED, magnitude: {var}')

            self.iteration += 1