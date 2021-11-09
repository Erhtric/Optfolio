"""
THIS FILE CONTAINS THE METHODS FOR THE SIMPLEX ALGORITHM EXECUTION.
"""
import matplotlib
import numpy as np
from matplotlib import pyplot as plt
from warnings import warn

class Simplex:
    """
    This class includes the Simplex algorithm and the method associated. As it is, it can
    be used to solve any linear optimization problem. In this specific project, it will be
    used to solve a portfolio o/ptimization problem, even though there are faster method to do so.
    """

    def __init__(self
                , c: np.array
                , A: np.array
                , b: np.array
                , verbose=False
                , max_iteration=1000) -> None:
        """
        Initializes a Simplex session in the standard form
            max c.T @ X s.t. A @ X = b
        where:
            - c is the vector of coefficients for the objective function
            - A is the matrix of coefficients for the constraint equations
            - b is the vector of constants on the RHS of the constraint equations
            - max is the type of problem: True if we are maximizing and False if we are minimizing
        """
        # Array of coefficients of the objective function
        self.of_params = c.reshape((1, c.shape[0]))
        # Matrix of coefficients of the constraints
        self.bounds_params = A
        # Array of constants
        self.constants = b.reshape((b.shape[0], 1))

        # Array of solutions
        # since the tableau is ordered from left to right we need only the number of original variables in the problem
        self.tableau = []
        self.n_vars = np.count_nonzero(self.of_params)
        self.solutions = np.zeros(self.n_vars)
        self.slack = np.zeros(self.constants.shape[0])
        # To apply the Cunningham's rule (or round-robin rule)
        # We create a random cyclic ordering for choosing the variable that will enter the basis
        self.variable_ordering = np.arange(self.n_vars)
        np.random.shuffle(self.variable_ordering)
        self.order_count = 0

        # value of the objective function
        self.objective = []
        # Number of Simplex iterations, 0 is the starting point
        self.iteration = 0
        self.verbose = verbose
        self.max_iteration = max_iteration

        self.dual_t = None
        self.dual_y = None

    def create_tableau(self):
        """
        Create the tableau. From left to right, the column identify a different
        variable or constant; indeed we will have all the non-basic variables,
        then the slack variables.

        tableau\n
        = [ A [0] b
            c  1  0]
        where c is the vector of the coefficients of the objective function
        """
        Ab = np.array([np.concatenate((p, [0], b)) for p, b in zip(self.bounds_params, self.constants)], dtype=np.float64)
        # the objective function should be correctly negated (based on the type of optimization we are doing)
        z = np.append(self.of_params, [1, 0]).reshape((Ab.shape[1], 1))
        self.tableau = np.concatenate((Ab, z.T), axis = 0)

    def __is_optimal(self) -> bool:
        """A solution is optimal, in a maximization problem, if in every term in the objective function is non-negative
        (in a minimization problem, non-positive).
        """
        c = self.tableau[-1, :-2]
        return all(val <= 0 for val in c)

    def __is_basic(self, idx) -> bool:
        """Checks if the column at index idx is a unit-column, then the variable associated
        is a basic variable. If it is not the case the variable it is a non-basic one.
        A unit column is a vector which has one and exactly one value equal to one and the others
        are equal to zero.
        """
        return [True if el==0 else False for el in self.tableau[:, idx]].count(True) == \
                    self.tableau[:, idx].shape[0] - 1 and np.sum(self.tableau[:, idx]) == 1

    def __nonbasic_var_indexes(self) -> list:
        """Return the list of indexes where each column is a unit-column"""
        indexes = []
        for c in range(self.tableau.shape[1] - 2):
            if not self.__is_basic(c):
                indexes.append(c)
        return indexes

    def __compute_pivot_col_position(self, rule) -> int:
        """This method simply computes the column index for the pivot in the tableau.
        If a solution is non optimal, then one or more terms in the last row of the tableau
        are negative, this is done by taking the minimum value among those values. The
        opposite holds if we are taking a minimization problem.
        """
        nonbasic = self.tableau[-1, self.__nonbasic_var_indexes()]
        idx = None

        # Pivoting rule, to avoid degeneracy
        if rule == 'largest':
            #idx = np.argmin(z, axis=0) if self.maximization else np.argmin(z, axis=0)
            idx = np.argmax(nonbasic, axis=0)
        elif rule == 'cunningham':
            idx = self.variable_ordering[self.order_count]
            self.order_count = (self.order_count + 1) % self.n_vars           # following Cunningham's rule
        elif rule == 'random':
            idx = self.variable_ordering[np.random.randint(self.n_vars)]
        return idx

    def __compute_pivot_row_position(self) -> int:
        """This method computes the row index for the pivot in the tableau by performing
        the min-ratio test.
        If a solution is non optimal, and given the pivoting column the index for the
        row will be the minimum value obtained as the result from dividing the corresponding
        constant by the target element indicized by the row pivoting index.
        """
        col_idx = self.__compute_pivot_col_position('largest')
        A = self.tableau[:-1, :]
        temp = []
        for row in A:
            target = row[col_idx]
            b = row[-1]
            # this last operation is crucial: since we have to divide by the elements
            # in the coefficient matrix it is important to identify the elements which are
            # equal to zero, in addition to the one which are not interesting for the algorithm
            # which are the negative ones (tagged as infinite)
            temp.append(np.inf if target <= 0 else b / target)

        # If all the elements in the temporary memory are infinite, then it is impossible to improve
        # the tableau anymore and the program is then unbounded
        if all([val == np.inf for val in temp]):
            raise Exception("STOPPED EXECUTION: LINEAR PROGRAM UNBOUNDED")

        if self.verbose: print(f'Min-ratios list: {temp}')
        return np.argmin(temp)

    def get_pivot_position(self) -> tuple:
        """Computes the pivot position for the current tableau.
        """
        return self.__compute_pivot_row_position(), self.__compute_pivot_col_position('largest')

    def __sub_pivoting_1(self, row_idx, col_idx):
        """Part 1 of the pivot-changing part: the goal of this
        method is to set the pivot to 1 by multiplying the corresponding row by a certain factor"""
        pivot = self.tableau[row_idx, col_idx]
        if pivot == 0: warn('Degeneracy')
        self.tableau[row_idx, :] = self.tableau[row_idx, :] / pivot
        # print(f'Dividing by {pivot}')

    def __sub_pivoting_2(self, row_idx, col_idx):
        """Part 2 of the pivot-changing part: the goal of this
        method is to set the terms in the colum, apart from the pivot to 0"""
        for i in range(self.tableau.shape[0]):
            row = self.tableau[i, :]
            # To set the term in the pivot column to zero we have to subtract the
            # value from the entire row.
            # print(f'Subtracting by {row[col_idx]}')
            if i != row_idx and row[col_idx] != 0:
                # The operation is: R_i = R_i - mul * R_p
                pivot_row = self.tableau[row_idx, :]
                multiplier = row[col_idx]
                self.tableau[i, :] = row - multiplier * pivot_row

    def apply_pivoting(self):
        """This method apply the pivoting step to the tablueau by
        finding an appropriate pivot to then change the accordingly the values.
        This method modifies the tableau values.
        """
        row, col = self.get_pivot_position()
        if self.verbose:
            #print(f'Pivot position at iteration {self.iteration}: ({row}, {col})')
            print(f'Variable x_{col} enter the basis, Slack variable s_{row} leave the basis, pivoting...')

        self.__sub_pivoting_1(row, col)
        self.__sub_pivoting_2(row, col)

    def extract_solution(self):
        """This method guess the solution from the tableau which has to be optimal.
        A solution is composed by the non-basic variables' coefficients that appear in the first and the
        last optimal tableau and its relative constant values.
        """
        for col in range(self.tableau.shape[1] - 2):
            if self.__is_basic(col):
                row_idx = np.argmax(self.tableau[:, col])
                if col < self.n_vars:
                    # THIS IS A SOLUTION VARIABLE
                    self.solutions[col] = self.tableau[row_idx, -1]
                else:
                    # THIS IS A SLACK VARIABLE
                    self.slack[col - self.n_vars] = self.tableau[row_idx, -1]
            else:
                if col < self.n_vars:
                    # THIS IS A SOLUTION VARIABLE
                    self.solutions[col] = 0
                else:
                    # THIS IS A SLACK VARIABLE
                    self.slack[col - self.n_vars] = 0
        self.objective.append(self.tableau[-1, -1])

    def __extract_dual_solution(self):
        z = self.tableau[-1, :]
        self.dual_t = z[:self.n_vars]
        self.dual_y = z[self.n_vars:-2]

    def solve(self) -> np.array:
        """Main method of the class. It needs to be called in order to get
        an array of solutions. It iteratively search for a solution by applying a pivoting operation
        to the tableau until the current set of solutions is optimal.
        """
        self.create_tableau()
        if self.verbose: print(f'tableau iteration {self.iteration}: \n{self.tableau}')

        while not self.__is_optimal() and self.iteration < self.max_iteration:
            if self.verbose: print(f'Objective function value: {self.tableau[-1, -1]}')
            self.objective.append(self.tableau[-1, -1])

            self.apply_pivoting()
            self.iteration += 1
            if self.verbose: print(f'Tableau iteration {self.iteration}: \n{self.tableau}')

        if self.verbose:
            print(f'Objective function value: {self.tableau[-1, -1]}')
            print(f'Tableau iteration {self.iteration+1}: \n{self.tableau}')

        self.extract_solution()
        self.__extract_dual_solution()
        return self.solutions

    def print_solution(self):
        if self.__is_optimal():
            print(f"Optimal solution found in {self.iteration} iterations")
            print('The feasible primal program is:')
            print(f"Solution variables: \t{self.solutions}")
            print(f"Slack variables: \t{self.slack}")
            print(f'The primal objective function has value: {self.tableau[-1, -1]}')

            if self.verbose:
                print()
                print('The feasible dual program is:')
                print(f"Solution dual variables: {self.dual_t}")
                print(f"Slack dual variables: \t{self.dual_y}")
                print(f'Complementary slackness conditions satisfied: {not bool(self.dual_t.T @ self.solutions and self.dual_y.T @ self.slack)}')
        else:
            print(f"Non-Optimal solution found in {self.iteration} iterations")
            print('The feasible primal program is:')
            print(f"Solution variables: \t{self.solutions}")
            print(f"Slack variables: \t{self.slack}")
            print(f'The primal objective function has value: {self.tableau[-1, -1]}')


    def plot_objective_function(self):
        matplotlib.use('TkAgg')
        # print(matplotlib.get_backend())
        fig = plt.figure()
        fig.suptitle('Objective Value History')
        plt.plot(np.arange(self.iteration+1), self.objective)
        plt.grid(True)
        fig.savefig(f'./src/results/objective_history_simplex.pdf')