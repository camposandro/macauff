"""Two sample benchmarks to compute runtime and memory usage.

For more information on writing benchmarks:
https://asv.readthedocs.io/en/stable/writing_benchmarks.html."""
import numpy as np
from macauff.counterpart_pairing_fortran import counterpart_pairing_fortran as cpf


def test_calculate_contamination_probabilities():
    rho = np.linspace(0, 100, 10000)
    drho = np.diff(rho)
    sigs = np.array([0.1, 0.2, 0.3, 0.4])
    seed = 96473
    rng = np.random.default_rng(seed)
    G = np.empty((len(rho) - 1, len(sigs)), float)
    for i in range(len(sigs)):
        G[:, i] = np.exp(-2 * np.pi ** 2 * (rho[:-1] + drho / 2) ** 2 * sigs[i] ** 2)
    for sep in rng.uniform(0, 0.5, 10):
        cpf.contam_match_prob(G[:, 0], G[:, 1], G[:, 2], G[:, 3], rho[:-1] + drho / 2, drho, sep)


def time_computation():
    """Time computations are prefixed with 'time'."""
    test_calculate_contamination_probabilities()


def peakmem_list():
    """Memory computations are prefixed with 'mem' or 'peakmem'."""
    test_calculate_contamination_probabilities()
