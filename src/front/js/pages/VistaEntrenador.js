import React from 'react'
import '../../styles/VistaEntrenador.css'
import { Link } from 'react-router-dom';

const VistaEntrenador = () => {
    return (
        <div className='vista-entrenador'>
            <div className='your-clients'>
                <h1>Your Clients</h1>

                <div className='lista-clientes'>
                    <div className='cliente'>
                        <p><strong>Client Name</strong></p>
                        <Link to="/trainer/cliente">
                        <button className='view-details'>View details</button>
                        </Link>
                    </div>
                    <div className='cliente'>
                    <p><strong>Client Name</strong></p>
                    <Link to="/trainer/cliente">
                        <button className='view-details'>View details</button>
                        </Link>
                    </div>
                    <div className='cliente'>
                    <p><strong>Client Name</strong></p>
                    <Link to="/trainer/cliente">
                        <button className='view-details'>View details</button>
                        </Link>
                    </div>
                    <div className='cliente'>
                        <p><strong>Client Name</strong></p>
                        <Link to="/trainer/cliente">
                        <button className='view-details'>View details</button>
                        </Link>
                    </div>
                </div>
            </div>
        </div>
    )
}

export default VistaEntrenador
