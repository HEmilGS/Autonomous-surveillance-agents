using System.Collections;
using System.Collections.Generic;
using UnityEngine;

public class fPlayer : MonoBehaviour
{
    public Transform player;
    public float mouseSensitivity = 2f;
    float cameraVerticalRotation = 0f;

    bool lockCursor = true;

    public float moveSpeed = 5f; // Velocidad de movimiento del jugador
    public float groundDistance = 0.1f; // Distancia de la "tierra" para detectar si estamos en el suelo
    public LayerMask groundLayer; // Capa para detectar el suelo

    // Start is called before the first frame update
    void Start()
    {
        Cursor.visible = false;
        Cursor.lockState = CursorLockMode.Locked;
    }

    // Update is called once per frame
    void Update()
    {
        // Movimiento de la cámara con el ratón
        float inputX = Input.GetAxis("Mouse X") * mouseSensitivity;
        float inputY = Input.GetAxis("Mouse Y") * mouseSensitivity;

        cameraVerticalRotation -= inputY;
        cameraVerticalRotation = Mathf.Clamp(cameraVerticalRotation, -90f, 90f);
        transform.localEulerAngles = Vector3.right * cameraVerticalRotation;
        player.Rotate(Vector3.up * inputX);

        // Movimiento del jugador con WASD
        float moveX = Input.GetAxis("Horizontal"); // A/D
        float moveZ = Input.GetAxis("Vertical"); // W/S

        // Crear un vector de dirección basado en la rotación de la cámara del jugador
        Vector3 moveDirection = player.right * moveX + player.forward * moveZ;

        // Aseguramos que el movimiento sea relativo a la cámara y que no se desplace en el eje Y
        moveDirection.y = 0;

        // Mover el jugador
        transform.Translate(moveDirection * moveSpeed * Time.deltaTime, Space.World);
    }
}
