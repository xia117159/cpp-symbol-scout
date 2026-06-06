#include <stdio.h>

#include <string>
#include <utility>

static bool bool_literal_issue(int value) {
	if (value > 0)
		return 1;
	return 0;
}

static void takes_string(std::string value) {
	(void)value;
}

static void performance_move_const_arg() {
	const std::string name = "godot";
	takes_string(std::move(name));
}

static void use_after_move() {
	std::string name = "node";
	std::string moved = std::move(name);
	printf("%s %s\n", name.c_str(), moved.c_str());
}

int main(void) {
	int *ptr = 0;
	if (ptr == 0)
		printf("null\n");
	use_after_move();
	performance_move_const_arg();
	return bool_literal_issue(1) ? 0 : 1;
}

