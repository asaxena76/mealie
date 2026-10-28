import { BaseAPI } from "../base/base-clients";
import type { CarrieAccepted, CarrieContext, CarrieHistory, CarrieSend, CarrieStatus } from "../types/carrie";

export class CarrieAPI extends BaseAPI {
  status() {
    return this.requests.get<CarrieStatus>("/api/households/carrie/status");
  }

  history(context: CarrieContext) {
    return this.requests.post<CarrieHistory>("/api/households/carrie/history", context);
  }

  send(message: CarrieSend) {
    return this.requests.post<CarrieAccepted>("/api/households/carrie/messages", message);
  }

  stop(context: CarrieContext) {
    return this.requests.post<null>("/api/households/carrie/stop", context);
  }
}
