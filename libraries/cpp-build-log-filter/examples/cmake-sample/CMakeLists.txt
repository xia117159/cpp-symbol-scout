cmake_minimum_required(VERSION 3.20)
project(cmake_sample CXX)

add_executable(cmake_sample main.cpp)
target_compile_features(cmake_sample PRIVATE cxx_std_17)
target_compile_options(cmake_sample PRIVATE -Wall -Wextra)
