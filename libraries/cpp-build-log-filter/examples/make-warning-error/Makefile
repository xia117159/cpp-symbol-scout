CXX ?= g++
CXXFLAGS ?= -std=c++17 -Wall -Wextra

.PHONY: all clean

all: app

app: main.o
	$(CXX) $(CXXFLAGS) -o $@ $^

main.o: main.cpp
	$(CXX) $(CXXFLAGS) -c $<

clean:
	rm -f app main.o
