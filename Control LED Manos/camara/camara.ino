//ESTE CODIGO LO DEBEN PEGAR EN EL ARDUINO IDE
#include <WebServer.h>//server
#include <WiFi.h>//conectarse a wifi
#include <esp32cam.h>//control de camara

const char* Nombre = "RivanCamWeb";
const char* Contrasena = "13440261";

//---configuracion del motor---
const int pinLed = 4;         //pin para el led
const int frecuencia = 5000;  //velocidad de la señal
const int canalPWM = 0;       //canal para el motor
const int resolucion = 8;     //resolucion de 0 a 255

WebServer server(80);

static auto fixedRes = esp32cam::Resolution::find(800, 600); //dimensiones de la imagen

void serveJpg() {
  auto frame = esp32cam::capture();//captura imgen
  //si no captura una imgen da un mensake de error
  if (frame == nullptr) {
    Serial.println("Error al capturar img");
    server.send(503, "", "");
    return;
  }
  server.setContentLength(frame->size());//cuanto pesa la imagen que se mandara
  server.send(200, "image/jpeg");//indica que es una imgen jpeg
  WiFiClient client = server.client();//identifica al cliente 
  frame->writeTo(client);//envia la img
}

void manejarControl() {
  if (server.hasArg("potencia")) { //revisa si llego el dato potencia
    String valorTexto = server.arg("potencia");//guarda el texto recibido
    int valorPotencia = valorTexto.toInt();//lo convierte a numero
    valorPotencia = constrain(valorPotencia, 0, 255);//asegura rango de 0 a 255
    ledcWrite(canalPWM, valorPotencia);//manda la potencia al motor
    server.send(200, "text/plain", "ok");//responde al python
    Serial.print("Motor a: ");//imprime en monitor
    Serial.println(valorPotencia);//valor de la potencia
  }
}

void setup() {
  Serial.begin(115200);
  Serial.println();

  {
    using namespace esp32cam; //)
    Config cfg;               //}cambiamos el esp32:: por cfg
    cfg.setPins(pins::AiThinker);//configura los pines automatico
    cfg.setResolution(fixedRes);//aplica el tamaño de la imagen(fixedRes)
    cfg.setBufferCount(2);//2 espacios para que no se detenga la captura de imagen
    cfg.setJpeg(80); // Calidad de imagen (1-100)
    bool ok = Camera.begin(cfg);//inicia la camara con lo que tenga cfg y debuelve true o false 
    Serial.println(ok ? "Inicio de camara exitosa" : "Inicio de camara fallida");//
  }

  //---configuracion de salida motor---
  ledcSetup(canalPWM, frecuencia, resolucion);//crea el canal pwm
  ledcAttachPin(pinLed, canalPWM);//conecta el pin 12 al canal

  WiFi.persistent(false);//mantiene los datos del wifi(nombre y contra) solo en la ram

  WiFi.mode(WIFI_AP);
  WiFi.softAP(Nombre, Contrasena);

  Serial.println("Red WiFi creada");
  Serial.print("IP del ESP32CAM: ");
  Serial.println(WiFi.softAPIP());

  Serial.println("\nWiFi Conectado");
  Serial.print("URL de la imagen: http://");
  Serial.print(WiFi.softAPIP());
  Serial.println("/cam.jpg");
  
  server.on("/cam.jpg", serveJpg);//ruta para la imagen
  server.on("/control", manejarControl);//ruta para recibir datos del motor
  server.begin();//inicia el server
}

void loop() {
  server.handleClient();//espera una peticion y usa el server.on
}