import type { RoomState } from "../api/types";

export type RoomTrigger =
  | "check_in"
  | "check_out"
  | "clean_done"
  | "set_dirty"
  | "lock_for_arrival"
  | "release_arrival"
  | "start_maintenance"
  | "end_maintenance"
  | "set_out_of_service"
  | "restore_service"
  | "room_swap";

export const ROOM_STATE_LABELS: Record<RoomState, string> = {
  vacant_clean: "空净",
  vacant_dirty: "空脏",
  occupied: "在住",
  arrival_locked: "锁房",
  maintenance: "维修",
  out_of_service: "停用",
};

export const TRIGGER_LABELS: Record<RoomTrigger, string> = {
  check_in: "入住",
  check_out: "退房",
  clean_done: "清扫完成",
  set_dirty: "置脏",
  lock_for_arrival: "锁房",
  release_arrival: "解锁",
  start_maintenance: "开始维修",
  end_maintenance: "结束维修",
  set_out_of_service: "停用",
  restore_service: "恢复使用",
  room_swap: "换房腾退",
};

// 镜像后端 app/domain/room_state.py 的合法流转，决定每个房态下可执行的动作
export const ALLOWED_TRIGGERS: Record<RoomState, RoomTrigger[]> = {
  vacant_clean: ["check_in", "set_dirty", "lock_for_arrival", "start_maintenance", "set_out_of_service"],
  vacant_dirty: ["clean_done", "lock_for_arrival", "start_maintenance", "set_out_of_service"],
  occupied: ["check_out"],
  arrival_locked: ["release_arrival", "check_in"],
  maintenance: ["end_maintenance", "set_out_of_service"],
  out_of_service: ["restore_service"],
};
