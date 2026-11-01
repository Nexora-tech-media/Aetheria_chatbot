import React from 'react'
import './style.css'
import { BiSupport } from "react-icons/bi";
import { FaPaperPlane } from "react-icons/fa";

const App = () => {
  return (
    <div className='absolute bottom-4 right-4 flex flex-col items-end'>
      <div className='bg-red-400 h-100 w-80 rounded-3xl'>
        <header className='flex items-center gap-4 font-primary bg-neutral-300'>
          <h1 className='bg-primary-100 py-2 px-4 rounded-full text-xl'>A</h1>
          <h1 className='font-bold text-md'>Aetheria Chatbot</h1>
        </header>

        <div>
          <input 
          type="text"
          placeholder='Ask me anything...'
          className='w-full'/>
          <button>
            <FaPaperPlane />
          </button>
        </div>
      </div>

      <button className='text-2xl text-black bg-primary p-2 mt-5 rounded-full'>
        <BiSupport />
      </button>
    </div>
  )
}

export default App