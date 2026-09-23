#!/bin/bash
# ContextOS Agent Setup Verification Script

echo "=========================================="
echo "ContextOS Agent Setup Verification"
echo "=========================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

checks_passed=0
checks_total=0

# Function to check file exists
check_file() {
    ((checks_total++))
    if [ -f "$1" ]; then
        echo -e "${GREEN}✅${NC} File exists: $1"
        ((checks_passed++))
        return 0
    else
        echo -e "${RED}❌${NC} File missing: $1"
        return 1
    fi
}

# Function to check executable
check_executable() {
    ((checks_total++))
    if [ -x "$1" ]; then
        echo -e "${GREEN}✅${NC} Executable: $1"
        ((checks_passed++))
        return 0
    else
        echo -e "${RED}❌${NC} Not executable: $1"
        return 1
    fi
}

# Function to check Python import
check_python_import() {
    ((checks_total++))
    if python3 -c "import $1" 2>/dev/null; then
        echo -e "${GREEN}✅${NC} Python module available: $1"
        ((checks_passed++))
        return 0
    else
        echo -e "${YELLOW}⚠️${NC}  Python module not available: $1 (optional)"
        ((checks_passed++))  # Don't fail on optional imports
        return 0
    fi
}

echo "1. Checking Core Files"
echo "----------------------"
check_file "run_contextos_agent.py"
check_executable "run_contextos_agent.py"
check_file "examples/agent_with_contextos.py"
check_executable "examples/agent_with_contextos.py"
echo ""

echo "2. Checking Documentation"
echo "-------------------------"
check_file "QUICK_START.md"
check_file "AGENT_RUNNER_README.md"
check_file "AGENT_INTEGRATION_SUMMARY.md"
echo ""

echo "3. Checking Python Dependencies"
echo "--------------------------------"
check_python_import "contextos"
check_python_import "grpc"
check_python_import "claude_agent_sdk"
echo ""

echo "4. Checking ContextOS SDK"
echo "-------------------------"
((checks_total++))
if [ -d "sdk/python/contextos" ]; then
    echo -e "${GREEN}✅${NC} ContextOS SDK directory exists"
    ((checks_passed++))
else
    echo -e "${RED}❌${NC} ContextOS SDK directory missing"
fi

((checks_total++))
if [ -f "sdk/python/contextos/client.py" ]; then
    echo -e "${GREEN}✅${NC} ContextOS client module exists"
    ((checks_passed++))
else
    echo -e "${RED}❌${NC} ContextOS client module missing"
fi
echo ""

echo "5. Testing Script Help"
echo "----------------------"
((checks_total++))
if python3 run_contextos_agent.py --help > /dev/null 2>&1; then
    echo -e "${GREEN}✅${NC} Script help command works"
    ((checks_passed++))
else
    echo -e "${RED}❌${NC} Script help command failed"
fi
echo ""

echo "6. Checking Docker (Optional)"
echo "-----------------------------"
((checks_total++))
if command -v docker &> /dev/null; then
    echo -e "${GREEN}✅${NC} Docker is installed"
    ((checks_passed++))
else
    echo -e "${YELLOW}⚠️${NC}  Docker not found (needed for --start-services)"
    ((checks_passed++))  # Don't fail
fi

((checks_total++))
if command -v docker-compose &> /dev/null; then
    echo -e "${GREEN}✅${NC} docker-compose is installed"
    ((checks_passed++))
else
    echo -e "${YELLOW}⚠️${NC}  docker-compose not found (needed for --start-services)"
    ((checks_passed++))  # Don't fail
fi
echo ""

echo "=========================================="
echo "Results: $checks_passed/$checks_total checks passed"
echo "=========================================="
echo ""

if [ $checks_passed -eq $checks_total ]; then
    echo -e "${GREEN}🎉 All checks passed! Setup is complete.${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. Start ContextOS: ./run_contextos_agent.py --start-services"
    echo "  2. Run demo: ./run_contextos_agent.py --demo"
    echo "  3. Try interactive: ./run_contextos_agent.py --interactive"
    echo ""
    exit 0
else
    missing=$((checks_total - checks_passed))
    echo -e "${YELLOW}⚠️  $missing checks failed or had warnings.${NC}"
    echo ""
    echo "You can still use the agent runner, but some features may not work."
    echo "See AGENT_RUNNER_README.md for setup instructions."
    echo ""
    exit 1
fi
