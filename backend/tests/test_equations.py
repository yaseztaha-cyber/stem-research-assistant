import sys
sys.path.insert(0, ".")
from backend.app.utils.text import extract_equations, explain_variables

def test_equation_extraction():
    text = "Efficiency is defined as eta = Pout / Pin, where P is power. Key equation: V = S * DeltaT. Also P = V * I."
    eqs = extract_equations(text)
    assert any("V = S" in e for e in eqs) or any("P = V" in e for e in eqs)
    # Ohm
    text2 = "Ohm's law: V = I * R governs internal behavior."
    eqs2 = extract_equations(text2)
    assert len(eqs2) >= 1

def test_variable_explanation():
    vars = explain_variables("V = I * R")
    assert "V" in vars
    assert vars["V"]["meaning"] == "voltage"
    vars2 = explain_variables("P = V * I")
    assert "P" in vars2

if __name__ == "__main__":
    test_equation_extraction()
    test_variable_explanation()
    print("equation tests passed")
