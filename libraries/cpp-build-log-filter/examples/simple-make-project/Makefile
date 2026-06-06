CXX ?= g++
CXXFLAGS ?= -std=c++17 -Wall -Wextra -Iinclude
BUILD_DIR := build

.PHONY: all clean

all: $(BUILD_DIR)/app

$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

$(BUILD_DIR)/app: $(BUILD_DIR)/main.o | $(BUILD_DIR)
	$(CXX) $(CXXFLAGS) -o $@ $^

$(BUILD_DIR)/main.o: src/main.cpp include/noisy.hpp | $(BUILD_DIR)
	$(CXX) $(CXXFLAGS) -c $< -o $@

clean:
	rm -rf $(BUILD_DIR)
