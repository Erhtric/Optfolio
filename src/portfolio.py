import data
import pandas as pd
import numpy as np
import os
from solvers import simplex
from solvers import interior_point
from typing import List

class Portfolio:

    def __init__(self, tickers: List[str]
                , lower: np.array
                , upper: np.array
                , start_date: str
                , end_date: str):
        """
        Initializes a portfolio instance

        Args:
            tickers: a list of assets to be included in the portfolio
            lower: numpy array describing the lower bounds
            upper: numpy array describing the upper bounds
            start_date: the starting date for the historical data
            end_date: the ending date for the historical data
        """
        self.tickers = tickers
        self.market_data = self.get_market_data(start_date, end_date)
        self.start_date = start_date
        self.end_date = end_date

        if lower.shape[0] != len(self.tickers) or upper.shape[0] != len(self.tickers) or \
            any(l > 1.0 for l in lower) or any(u > 1.0 for u in upper):
            raise Exception("STOPPED EXECUTION: PORTFOLIO NOT INITIALIZED - PLEASE INSERT LEGIT BOUND ARRAYS")
        else:
            self.lb = lower.reshape((lower.shape[0], 1))
            self.ub = upper.reshape((upper.shape[0], 1))

        # WEIGHTS initialization
        # self.weights = np.ones((len(tickers), 1))
        # self.weights = self.weights / self.weights.sum(axis=0, keepdims=True)

        self.weights = []
        self.n_assets = len(tickers)

    ##################          PORTFOLIO METHODS            ###############################

    def get_market_data(self
                        , start_date: str
                        , end_date: str) -> pd.DataFrame:
        # TO REMOVE IF YAHOOFINANCIALS IS NOT PRESENT
        if not os.path.isfile(f'./src/data/ASSET_DATA_{start_date}_to_{end_date}_{self.tickers}.csv'):
            print('File not found, initializing download session')
            data.get_history_data(self.tickers, start_date, end_date)

        df = pd.read_csv(f'./src/data/ASSET_DATA_{start_date}_to_{end_date}_{self.tickers}.csv').set_index('formatted_date')
        return df

    def compute_returns(self) -> pd.DataFrame:
        """Compute the percentized gain/loss on the portfolio over the fixed timeframe specified at initialization.
        We make a return as the percentage chenge in the closing price of the asset over the previous day's closing price.
        """
        close_prices = pd.DataFrame()
        for count, ticker in enumerate(self.tickers):
            close_prices.insert(count, f"{ticker}", self.market_data['adjclose'][self.market_data['ticker']==ticker])
        return close_prices.pct_change()

    def compute_individual_expected_returns(self) -> pd.DataFrame:
        """Compute the average return for each asset.

        This method will be useful for the optimization part. Following the definition of the
        expected value we are computing the means of the individual assets instead of the expected value of the entire portfolio.
        """
        return self.compute_returns().mean()

    def compute_returns_covariance_matrix(self) -> pd.DataFrame:
        """Compute the covariance matrix between the assets' returns. It has been annualized to the 252 trading days.
        """
        return self.compute_returns().cov() * 252

    def compute_portfolio_return(self) -> pd.DataFrame:
        """Computes the expected portfolio's expected return defined as the weighted sum of the returns on the assets of the portfolio.
        """
        return self.compute_returns() @ self.weights

    def compute_portfolio_variance(self) -> np.float64:
        """Compute the total portfolio's variance.
        """
        return (self.weights.T @ self.compute_returns_covariance_matrix().to_numpy() @ self.weights)

    def compute_portfolio_std(self) -> np.float64:
        """Computes the portfolio's standard deviation, also called the volatily of the portfolio"""
        return np.sqrt(self.compute_portfolio_variance())

    ##################          OPTIMIZATION METHODS (SIMPLEX) - LP         ################
    # In this part there are the methods to optimize the linear portfolio problem of the maximum expected return
    # Obviously it will not produce satisfactory results.

    def preprocess_matrix_lp(self):
        """Produces a matrix in the standard form. Below an example for 2 assets:
        [1 0 1 0  0 0  0 0 ub1]
        [0 1 0 1  0 0  0 0 ub2]
        [1 1 0 0  0 0  0 0   1]
        [mu mu 0  0 0  0 0 0 0]
        where slack variables has been introduced.
        """
        matrix = np.zeros((self.ub.shape[0] + 2, self.n_assets + self.ub.shape[0] + 1))

        self.__set_bounds_coeff(matrix)
        self.__set_full_investment(matrix)
        self.__set_utility_function(matrix)
        return matrix

    def __set_full_investment(self, matrix):
        """Set the FULL-INVESTMENT CONSTRAINT, it requires thath all the coefficients for the variables
        to be equal to 1.0.
        """
        for c in range(len(self.tickers)):
            matrix[-2, c] = 1.0
        matrix[-2, -1] = 1.0

    def __set_utility_function(self, matrix):
        """Set the utility function as specified by the MAXIMUM EXPECTED RETURN PORTFOLIO where
        the utility function is the following:
            u = exp_p
        with exp_p the expected return of the portfolio.
        """
        individual_exp = self.compute_individual_expected_returns().to_numpy()
        for i in range(self.n_assets):
            matrix[-1, i] = individual_exp[i]

    def __set_bounds_coeff(self, matrix):
        """Set the constants for the upper bound. We already know that in a standard allocation problem
        the bound equations are in the following form:
            - w0 <= ub0, w1 <= ub1, ..., wn <= ubn -> wi + si = ubi
        """
        for r in range(self.ub.shape[0]):
            # The first ub rows are for the upper bound (<=)
            # The constants are by definition all nonnegative!
            # To convert into equation we need to add a SLACK variable
            matrix[r,  r] = 1                                   # for the variable
            matrix[r, -1] = self.ub[r]
            matrix[r,  r + self.ub.shape[0]] = 1.0              # for the slack variable
        return matrix

    def split_matrix_lp(self):
        """Split the matrix in 3 components: the arrays of constants and objective function
        and the constraint + slack matrix"""
        matrix = self.preprocess_matrix_lp()
        A = matrix[:-1, :-1]
        b = matrix[:-1, -1]
        c = matrix[-1, :-1]
        return c, A, b

    def solve_simplex_LP(self, verbose=False):
        """Tries to solve the portfolio problem of the maximum expected return
        by using a simplex solver.
        """
        c, A, b = self.split_matrix_lp()
        slex = simplex.Simplex(c, A, b, verbose=verbose)
        slex.solve()
        if verbose: slex.print_solution()
        self.weights = slex.solutions

    ##################          OPTIMIZATION METHODS (INTERIOR POINT) - QP         ################

    def preprocess_matrix_qp(self):
        """Split the matrix in 3 components: the arrays of constants and objective function
        and the constraint matrix"""
        A = np.zeros((self.ub.shape[0] + 1, self.n_assets))
        for r in range(self.n_assets):
            A[r, r] = -1
        A[-1] = np.ones(self.n_assets)
        c = np.zeros(self.n_assets)
        b = np.append(-self.ub, 1)
        return c, A, b

    def solve_intpoint_QP(self, verbose=False):
        """Tries to solve the portfolio problem of the mean-variance portfolio by using an interior-point
        method.
        """
        c, A, b = self.preprocess_matrix_qp()
        S = self.compute_returns_covariance_matrix()

        init_point = (np.random.uniform(0.0, 1.0, [self.n_assets,])
                    , np.random.uniform(0.1, 100.0, [A.shape[0],])
                    , np.random.uniform(0.1, 100.0, [A.shape[0],]))

        intpoint = interior_point.IntPoint(S, c, A, b
                                        , verbose=verbose
                                        , x_init=init_point[0]
                                        , y_init=init_point[1]
                                        , lm_init=init_point[2]
                                        , max_iteration=100
                                        )
        intpoint.solve()
        if verbose: intpoint.print_solution()
        self.weights = intpoint.hsol[-1]

    ##################          OUTPUT METHODS            ##########################################

    def print_stats(self):
        print('Portfolio data:')
        print(f' - assets: {self.tickers}')
        print(f' - assets participations: {list(self.weights)}')
        print(f' - portfolio variance: {self.compute_portfolio_variance():.4f}')
        print(f' - portfolio standard deviation (risk): {self.compute_portfolio_std():.4f}')
        print(f' - portfolio current expected return: {np.mean(self.compute_portfolio_return()):.4f}')