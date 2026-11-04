import sympy as sp

def symbolic_integral(expr, var, a=None, b=None):
    """Return the symbolic integral of expr with respect to var.
    If a and b are provided, return the definite integral from a to b."""
    x = sp.Symbol(var)
    integral = sp.integrate(expr, x)
    if a is not None and b is not None:
        return sp.integrate(expr, (x, a, b))
    return integral

def numeric_integral(expr, var, a, b, n=1000):
    """Approximate the definite integral of expr from a to b using the trapezoidal rule."""
    x = sp.Symbol(var)
    f = sp.lambdify(x, expr, 'numpy')
    import numpy as np
    xs = np.linspace(a, b, n+1)
    ys = f(xs)
    return np.trapz(ys, xs)

if __name__ == "__main__":
    # Example usage
    x = sp.Symbol('x')
    expr = sp.exp(-x**2)
    print("Symbolic integral:", symbolic_integral(expr, 'x'))
    print("Definite integral 0 to 1:", symbolic_integral(expr, 'x', 0, 1))
    print("Numeric integral 0 to 1:", numeric_integral(expr, 'x', 0, 1))
