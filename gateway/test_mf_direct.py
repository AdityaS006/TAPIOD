from routellm.routers.matrix_factorization import MatrixFactorizationRouter

# Try instantiating the MF router directly
print("Initializing MF router directly...")
router = MatrixFactorizationRouter()

try:
    score = router.calculate_score("What is 2+2?")
    print("Direct router score:", score)
except Exception as e:
    print("Error calculating score directly:", e)

# Let's also see what methods it has
print(dir(router))
