#include <assert.h>
#include "native-answer.h"
int main(int argc, char **argv) {
  assert(answer_init(argc, argv) == 0);
  for (uint32_t value = 0; value < 100; value++) {
    assert(native_answer(value) == value + EXPECTED);
    answer_collect();
  }
  assert(native_answer(UINT32_MAX) == EXPECTED - 1);
  return 0;
}
