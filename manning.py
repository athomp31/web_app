def manning_flow(n, A, R, S):
    """Calculate open-channel flow in cfs for Manning's equation.

    n is Manning's roughness coefficient, A is area in ft², R is hydraulic
    radius in ft, and S is the channel slope. Returns flow Q in cfs.
    """
    return (1.49 / n) * A * R ** (2 / 3) * S ** 0.5